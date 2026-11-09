/**
 * Career contracts on the session blackboard.
 *
 * The play loop records a prose board (`discoveries` / `career.board`), the accepted
 * contract (`lessons` / `career.accept.*`), the current goal (`goals` / `career.current`),
 * and a miss (`lessons` / `career.fail.*`). A structured snapshot (`offered`, `active`,
 * `parameters`) is used when an entry already carries one.
 */

export interface BoardEntry {
  section: string;
  key: string;
  value?: unknown;
}

export interface ContractParameter {
  label: string;
  state: "open" | "done" | "failed";
  optional: boolean;
}

export interface ListedContract {
  title: string;
  kind: string;
  parameters: ContractParameter[];
  reward: string | null;
  alreadyActive: boolean;
}

export interface AcceptedContract {
  title: string;
  summary: string;
  kind: string | null;
  parameters: ContractParameter[];
  goals: string[];
  reward: string | null;
}

export interface MissLesson {
  title: string;
  lesson: string;
}

export interface ContractBoardModel {
  /** True once a career note or contract snapshot has been read. */
  reported: boolean;
  economy: string | null;
  notices: string[];
  offered: ListedContract[];
  accepted: AcceptedContract | null;
  misses: MissLesson[];
}

interface AcceptNote {
  title: string;
  summary: string;
  contractKey: string | null;
  kind: string | null;
}

interface GoalNote {
  text: string;
  contractKey: string | null;
}

const MISS_TEXT = /^Do not accept contract key `[^`]*` \(([^)]+)\) again:\s*([\s\S]+)$/i;

export function plainContractKind(raw: string): string {
  const leaf = raw.split(".").pop()?.trim() || raw.trim();
  const spaced = leaf
    .replace(/[_-]+/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/\s+/g, " ")
    .trim();
  if (!spaced) return "Contract";
  const lower = spaced.toLowerCase();
  if (lower === "contract") return "Contract";
  return `${lower.charAt(0).toUpperCase()}${lower.slice(1)}`;
}

export function contractBoardFromEntries(entries: readonly BoardEntry[]): ContractBoardModel {
  const notices: string[] = [];
  const acceptNotes: AcceptNote[] = [];
  const goalNotes: GoalNote[] = [];
  const misses: MissLesson[] = [];
  let reported = false;
  let economy: string | null = null;
  let proseOffered: ListedContract[] = [];
  let proseActive: ListedContract[] = [];
  let structured: { offered: ListedContract[]; active: ListedContract[]; economy: string | null } | null =
    null;

  for (const entry of entries) {
    const value = asRecord(entry.value);
    const snapshot = readSnapshot(entry.value);
    if (snapshot) {
      structured = snapshot;
      reported = true;
    }

    if (entry.section === "discoveries" && entry.key === "career.board" && value) {
      const text = textOf(value);
      if (text) {
        const parsed = parseBoard(text);
        economy = parsed.economy;
        proseOffered = parsed.offered;
        proseActive = parsed.active;
        reported = true;
      }
    }

    if (entry.section === "discoveries" && value) {
      const text = textOf(value);
      const notice =
        entry.key === "career.mode" ||
        entry.key === "career.idle" ||
        entry.key.startsWith("career.unparsed.");
      if (text && notice) {
        notices.push(stripCodes(text));
        reported = true;
      }
    }

    if (entry.section === "lessons" && value && isAccept(entry.key, value)) {
      const title = stringField(value, "contract_title");
      const summary = stripCodes(textOf(value) ?? "");
      if (title && summary) {
        reported = true;
        acceptNotes.push({
          title,
          summary,
          contractKey: stringField(value, "contract_key"),
          kind: stringField(value, "contract_type")
            ? plainContractKind(stringField(value, "contract_type") ?? "")
            : null,
        });
      }
    }

    if (entry.section === "lessons" && value && isMiss(entry.key, value)) {
      reported = true;
      misses.push(missLesson(textOf(value) ?? "", stringField(value, "contract_title")));
    }

    if (entry.section === "goals" && value) {
      const text = textOf(value);
      if (text && (entry.key === "career.current" || stringField(value, "contract_key"))) {
        reported = true;
        goalNotes.push({ text: stripCodes(text), contractKey: stringField(value, "contract_key") });
      }
    }
  }

  const structuredLists =
    structured && (structured.offered.length > 0 || structured.active.length > 0) ? structured : null;
  const offered = structuredLists?.offered ?? proseOffered;
  const active = structuredLists?.active ?? proseActive;
  const accepted = chooseAccepted(acceptNotes, offered, active, goalNotes);
  const acceptedTitle = accepted ? normalize(accepted.title) : null;
  const extras = active
    .filter((contract) => normalize(contract.title) !== acceptedTitle)
    .filter((contract) => !offered.some((row) => normalize(row.title) === normalize(contract.title)))
    .map((contract) => ({ ...contract, alreadyActive: true }));

  return {
    reported,
    economy: economy ?? structured?.economy ?? null,
    notices: unique(notices.filter((line) => line.length > 0)),
    offered: [...offered, ...extras],
    accepted,
    misses: uniqueBy(misses, (row) => `${normalize(row.title)}|${row.lesson}`),
  };
}

function chooseAccepted(
  acceptNotes: AcceptNote[],
  offered: ListedContract[],
  active: ListedContract[],
  goalNotes: GoalNote[],
): AcceptedContract | null {
  const goalKey = goalNotes.find((goal) => goal.contractKey)?.contractKey ?? null;
  const goalTitle = goalNotes.map((goal) => titleFromGoal(goal.text)).find((title) => title !== null) ?? null;
  const picked = pickAccept(acceptNotes, active, goalKey, goalTitle);
  const title = picked?.title ?? goalTitle ?? (active.length === 1 ? active[0]?.title : null);
  if (!title) return null;
  const listed = findContract(active, title) ?? findContract(offered, title);
  const goals = goalNotes
    .filter((goal) => goalBelongs(goal, picked?.contractKey ?? goalKey, title))
    .map((goal) => goal.text);
  return {
    title,
    summary: picked?.summary ?? "This contract is active.",
    kind: listed?.kind ?? picked?.kind ?? null,
    parameters: listed?.parameters ?? [],
    reward: listed?.reward ?? null,
    goals: unique(goals),
  };
}

function pickAccept(
  notes: AcceptNote[],
  active: ListedContract[],
  goalKey: string | null,
  goalTitle: string | null,
): AcceptNote | null {
  if (notes.length === 0) return null;
  if (goalKey) {
    const byKey = notes.find((note) => note.contractKey === goalKey);
    if (byKey) return byKey;
  }
  if (goalTitle) {
    const byTitle = notes.find((note) => normalize(note.title) === normalize(goalTitle));
    if (byTitle) return byTitle;
  }
  const activeTitles = new Set(active.map((contract) => normalize(contract.title)));
  const onActive = notes.filter((note) => activeTitles.has(normalize(note.title)));
  if (onActive.length === 1) return onActive[0] ?? null;
  if (notes.length === 1) return notes[0] ?? null;
  return onActive[0] ?? notes[notes.length - 1] ?? null;
}

function goalBelongs(goal: GoalNote, key: string | null, title: string): boolean {
  if (key && goal.contractKey) return goal.contractKey === key;
  if (goal.contractKey && !key) return false;
  const needle = normalize(title);
  return !goal.contractKey || normalize(goal.text).includes(needle);
}

function findContract(list: ListedContract[], title: string): ListedContract | undefined {
  const needle = normalize(title);
  return list.find((contract) => normalize(contract.title) === needle);
}

function titleFromGoal(text: string): string | null {
  const accepted = /^Accepted ['"]?(.+?)['"]?:/.exec(text);
  if (accepted?.[1]) return accepted[1].trim();
  const complete = /^Complete ['"]?(.+?)['"]?$/.exec(text);
  if (complete?.[1]) return complete[1].trim();
  const step = /^(.+?): /.exec(text);
  if (step?.[1]) return step[1].trim();
  return null;
}

function parseBoard(text: string): {
  economy: string | null;
  offered: ListedContract[];
  active: ListedContract[];
} {
  const offeredAt = text.indexOf("Offered:");
  const activeAt = text.indexOf("Active:");
  if (offeredAt < 0 || activeAt < offeredAt) {
    return { economy: null, offered: [], active: [] };
  }
  const economy = plainEconomy(text.slice(0, offeredAt));
  const offered = parseContractList(text.slice(offeredAt + "Offered:".length, activeAt), false);
  const active = parseContractList(text.slice(activeAt + "Active:".length), true);
  return { economy, offered, active };
}

function parseContractList(raw: string, alreadyActive: boolean): ListedContract[] {
  const body = raw.trim().replace(/\.+$/, "").trim();
  if (!body || body.toLowerCase() === "none") return [];
  return body
    .split(" | ")
    .map((phrase) => parsePhrase(phrase, alreadyActive))
    .filter((row): row is ListedContract => row !== null);
}

function parsePhrase(phrase: string, alreadyActive: boolean): ListedContract | null {
  const trimmed = phrase.trim().replace(/\.+$/, "").trim();
  if (!trimmed || trimmed.toLowerCase() === "none") return null;
  const match = /^(.+?) \[([^\]]+)\] — (.*)$/.exec(trimmed);
  if (!match?.[1] || !match[2] || match[3] === undefined) {
    return { title: trimmed, kind: "Contract", parameters: [], reward: null, alreadyActive };
  }
  const { params, reward } = splitParamsAndReward(match[3]);
  const parameters = params
    .split(";")
    .map((segment) => parseParam(segment))
    .filter((param) => param.label.length > 0);
  return {
    title: match[1].trim(),
    kind: plainContractKind(match[2]),
    parameters,
    reward,
    alreadyActive,
  };
}

function splitParamsAndReward(body: string): { params: string; reward: string | null } {
  const trimmed = body.trim().replace(/\.+$/, "").trim();
  if (trimmed === "no parameters") return { params: "", reward: null };
  if (trimmed.toLowerCase().startsWith("no parameters,")) {
    const reward = trimmed.slice("no parameters,".length).trim();
    return { params: "", reward: reward || null };
  }
  const close = trimmed.lastIndexOf(")");
  if (close >= 0) {
    const tail = trimmed.slice(close + 1).trim();
    if (tail.startsWith(",")) {
      const reward = tail.slice(1).trim();
      return { params: trimmed.slice(0, close + 1).trim(), reward: reward || null };
    }
  }
  return { params: trimmed, reward: null };
}

function parseParam(segment: string): ContractParameter {
  const trimmed = segment.trim();
  const match = /^(.*)\((open|done|failed)\)\s*$/i.exec(trimmed);
  if (!match?.[1] || !match[2]) return { label: trimmed, state: "open", optional: false };
  const state = match[2].toLowerCase();
  const parsed: ContractParameter["state"] = state === "done" || state === "failed" ? state : "open";
  return { label: match[1].trim(), state: parsed, optional: false };
}

function readSnapshot(
  value: unknown,
): { offered: ListedContract[]; active: ListedContract[]; economy: string | null } | null {
  const row = asRecord(value);
  if (!row) return null;
  const source = asRecord(row.career) ?? row;
  if (!Array.isArray(source.offered) && !Array.isArray(source.active)) return null;
  return {
    offered: readContractList(source.offered, false),
    active: readContractList(source.active, true),
    economy: economyFromSnapshot(source),
  };
}

function economyFromSnapshot(row: Record<string, unknown>): string | null {
  const bits: string[] = [];
  const funds = rounded(row.funds);
  const science = rounded(row.science);
  const reputation = rounded(row.reputation);
  if (funds) bits.push(`Funds ${funds}`);
  if (science) bits.push(`Science ${science}`);
  if (reputation) bits.push(`Reputation ${reputation}`);
  return bits.length > 0 ? bits.join(" · ") : null;
}

function readContractList(raw: unknown, alreadyActive: boolean): ListedContract[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => readContract(item, alreadyActive))
    .filter((row): row is ListedContract => row !== null);
}

function readContract(raw: unknown, alreadyActive: boolean): ListedContract | null {
  const row = asRecord(raw);
  const title = row ? stringField(row, "title") : null;
  if (!row || !title) return null;
  const parameters = Array.isArray(row.parameters)
    ? row.parameters
        .map((item) => readParam(item))
        .filter((param): param is ContractParameter => param !== null)
    : [];
  return {
    title,
    kind: plainContractKind(stringField(row, "type") ?? "contract"),
    parameters,
    reward: rewardFrom(row),
    alreadyActive,
  };
}

function readParam(raw: unknown): ContractParameter | null {
  const row = asRecord(raw);
  const title = row ? stringField(row, "title") : null;
  if (!title) return null;
  const failed = row?.failed === true;
  const completed = row?.completed === true;
  const optional = row?.optional === true;
  return {
    label: title,
    state: failed ? "failed" : completed ? "done" : "open",
    optional,
  };
}

function rewardFrom(row: Record<string, unknown>): string | null {
  const bits: string[] = [];
  const advance = rounded(row.funds_advance);
  const completion = rounded(row.funds_completion);
  const science = rounded(row.science_completion);
  const reputation = rounded(row.reputation_completion);
  if (advance) bits.push(`advance ${advance} funds`);
  if (completion) bits.push(`completion ${completion} funds`);
  if (science) bits.push(`${science} science`);
  if (reputation) bits.push(`${reputation} reputation`);
  return bits.length > 0 ? bits.join(", ") : null;
}

function rounded(value: unknown): string | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value === 0) return null;
  return String(Math.round(value));
}

function isAccept(key: string, value: Record<string, unknown>): boolean {
  if (value.ok === false || key.startsWith("career.done.")) return false;
  if (!stringField(value, "contract_title")) return false;
  if (key.startsWith("career.accept.")) return true;
  return stringField(value, "action_id") === "ksp.contract.accept" && value.ok === true;
}

function isMiss(key: string, value: Record<string, unknown>): boolean {
  if (key.startsWith("career.done.") || key.startsWith("career.accept.")) return false;
  if (key.startsWith("career.fail.")) return true;
  const text = textOf(value) ?? "";
  if (/do not accept contract key/i.test(text)) return true;
  if (value.ok !== false) return false;
  return Boolean(stringField(value, "contract_key") || stringField(value, "contract_title"));
}

function missLesson(text: string, title: string | null): MissLesson {
  const match = MISS_TEXT.exec(text.trim());
  const name = (title ?? match?.[1] ?? "This contract").trim();
  if (match?.[2]) {
    return { title: name, lesson: `${name} will not be accepted again. ${sentence(match[2])}` };
  }
  const stripped = stripCodes(text);
  return { title: name, lesson: stripped || `${name} will not be accepted again.` };
}

function plainEconomy(raw: string): string | null {
  const trimmed = raw.trim().replace(/\.+$/, "").trim();
  if (!trimmed) return null;
  const wrapped = /^([A-Za-z][A-Za-z ]*)\s*\((.*)\)\s*$/.exec(trimmed);
  if (wrapped?.[1] && wrapped[2]) {
    const bits = wrapped[2]
      .split(",")
      .map((part) => capitalize(part.trim()))
      .filter((part) => part.length > 0);
    return [wrapped[1].trim(), ...bits].join(" · ");
  }
  return trimmed
    .split(",")
    .map((part) => capitalize(part.trim()))
    .filter((part) => part.length > 0)
    .join(" · ");
}

function capitalize(text: string): string {
  if (!text) return "";
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
}

function stripCodes(text: string): string {
  return text
    .replace(/contract key `[^`]*`/gi, "")
    .replace(/`[^`]*`/g, "")
    .replace(/\b[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)+\b/g, "")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([.,])/g, "$1")
    .trim();
}

function sentence(text: string): string {
  const trimmed = stripCodes(text).replace(/\.+$/, "").trim();
  if (!trimmed) return "";
  return `${trimmed.charAt(0).toUpperCase()}${trimmed.slice(1)}.`;
}

function textOf(value: Record<string, unknown>): string | null {
  const text = value.text;
  if (typeof text !== "string") return null;
  const trimmed = text.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function stringField(value: Record<string, unknown>, key: string): string | null {
  const raw = value[key];
  if (typeof raw !== "string") return null;
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const record: Record<string, unknown> = {};
  for (const [key, entry] of Object.entries(value)) record[key] = entry;
  return record;
}

function normalize(text: string): string {
  return text
    .trim()
    .replace(/^['"]+|['"]+$/g, "")
    .toLowerCase();
}

function unique(lines: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const line of lines) {
    if (seen.has(line)) continue;
    seen.add(line);
    out.push(line);
  }
  return out;
}

function uniqueBy<T>(rows: T[], key: (row: T) => string): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const row of rows) {
    const id = key(row);
    if (seen.has(id)) continue;
    seen.add(id);
    out.push(row);
  }
  return out;
}
