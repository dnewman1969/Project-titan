import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";

import type {
  AcceptedContract,
  ContractBoardModel,
  ContractParameter,
  ListedContract,
} from "./contractBoard";

function stateLabel(parameter: ContractParameter): string {
  if (parameter.state === "done") return "Done";
  if (parameter.state === "failed") return "Failed";
  if (parameter.optional) return "Optional";
  return "Open";
}

function stateColor(parameter: ContractParameter): "success" | "warning" | "default" {
  if (parameter.state === "done") return "success";
  if (parameter.state === "failed") return "warning";
  return "default";
}

function ParameterList({ parameters }: { parameters: ContractParameter[] }) {
  return (
    <Stack spacing={0.5}>
      <Typography variant="caption" color="text.secondary">
        Parameters
      </Typography>
      {parameters.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No parameters reported yet.
        </Typography>
      ) : (
        parameters.map((parameter) => (
          <Stack
            key={`${parameter.label}:${parameter.state}`}
            direction="row"
            spacing={1}
            alignItems="center"
          >
            <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }}>
              {parameter.label}
            </Typography>
            <Chip
              size="small"
              variant="outlined"
              label={stateLabel(parameter)}
              color={stateColor(parameter)}
            />
          </Stack>
        ))
      )}
    </Stack>
  );
}

function OfferedCard({ contract }: { contract: ListedContract }) {
  return (
    <Box sx={{ pl: 1, borderLeft: 2, borderColor: "divider" }}>
      <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {contract.title}
        </Typography>
        {contract.kind !== "Contract" && (
          <Typography variant="caption" color="text.secondary">
            {contract.kind}
          </Typography>
        )}
        {contract.alreadyActive && <Chip size="small" variant="outlined" label="Active" />}
      </Stack>
      {contract.reward && (
        <Typography variant="body2" color="text.secondary">
          Reward: {contract.reward}
        </Typography>
      )}
      <ParameterList parameters={contract.parameters} />
    </Box>
  );
}

function AcceptedCard({ contract }: { contract: AcceptedContract }) {
  return (
    <Box sx={{ pl: 1, borderLeft: 2, borderColor: "primary.main" }}>
      <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {contract.title}
        </Typography>
        {contract.kind && contract.kind !== "Contract" && (
          <Typography variant="caption" color="text.secondary">
            {contract.kind}
          </Typography>
        )}
      </Stack>
      <Typography variant="body2">{contract.summary}</Typography>
      {contract.reward && (
        <Typography variant="body2" color="text.secondary">
          Reward: {contract.reward}
        </Typography>
      )}
      <Typography variant="caption" color="text.secondary">
        Goals
      </Typography>
      {contract.goals.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No goal reported yet.
        </Typography>
      ) : (
        contract.goals.map((goal) => (
          <Typography key={goal} variant="body2">
            {goal}
          </Typography>
        ))
      )}
      <ParameterList parameters={contract.parameters} />
    </Box>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Stack spacing={0.75}>
      <Typography component="h3" variant="subtitle2">
        {title}
      </Typography>
      {children}
    </Stack>
  );
}

/** Offered contracts, the accepted contract, and lessons from misses. */
export function ContractBoard({ model, emptyMessage }: { model: ContractBoardModel; emptyMessage: string }) {
  const populated = model.reported;
  return (
    <Stack spacing={1} aria-label="Contract board">
      {model.economy && (
        <Typography variant="caption" color="text.secondary">
          {model.economy}
        </Typography>
      )}
      {model.notices.map((notice) => (
        <Typography key={notice} variant="body2">
          {notice}
        </Typography>
      ))}
      {!populated ? (
        <Typography variant="body2" color="text.secondary">
          {emptyMessage}
        </Typography>
      ) : (
        <>
          <Section title="Accepted">
            {model.accepted ? (
              <AcceptedCard contract={model.accepted} />
            ) : (
              <Typography variant="body2" color="text.secondary">
                No contract has been accepted.
              </Typography>
            )}
          </Section>
          <Section title="Offered">
            {model.offered.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No contracts offered.
              </Typography>
            ) : (
              model.offered.map((contract) => <OfferedCard key={contract.title} contract={contract} />)
            )}
          </Section>
          <Section title="Lessons from misses">
            {model.misses.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No lessons from misses.
              </Typography>
            ) : (
              model.misses.map((miss) => (
                <Typography key={`${miss.title}:${miss.lesson}`} variant="body2">
                  {miss.lesson}
                </Typography>
              ))
            )}
          </Section>
        </>
      )}
    </Stack>
  );
}
