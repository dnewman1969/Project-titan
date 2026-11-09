import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useState } from "react";

import {
  useBrowseMemoryQuery,
  useDeleteMemoryItemsMutation,
  useLazySearchMemoryQuery,
  useMemoryStatusQuery,
  useWriteMemoryItemMutation,
} from "../../app/api";
import { formatApiError } from "../../app/formatApiError";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { setMemoryBrowserOpen, showNotice } from "../operations/layoutSlice";

type MemoryItem = {
  id: string;
  document?: string;
  metadata?: Record<string, string | number | boolean>;
  distance?: number;
};

/** AI → Memory Browser: search and curate persisted session learnings (M9.T4). */
export function MemoryBrowserDialog() {
  const dispatch = useAppDispatch();
  const open = useAppSelector((s) => s.layout.memoryBrowserOpen);
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const [gameSlug, setGameSlug] = useState("ksp");
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [searchItems, setSearchItems] = useState<MemoryItem[] | null>(null);
  const { data: status } = useMemoryStatusQuery(undefined, {
    skip: !open,
    pollingInterval: open ? 12000 : 0,
  });
  const {
    data: browseData,
    isFetching: browsing,
    refetch,
  } = useBrowseMemoryQuery({ gameSlug, limit: 40 }, { skip: !open, refetchOnMountOrArgChange: true });
  const [search, { isFetching: searching }] = useLazySearchMemoryQuery();
  const [writeItem, { isLoading: writing }] = useWriteMemoryItemMutation();
  const [deleteItems, { isLoading: deleting }] = useDeleteMemoryItemsMutation();

  const chromaState = status?.chroma.state ?? "unknown";
  const items = searchItems ?? (browseData?.items as MemoryItem[] | undefined) ?? [];

  const runSearch = async () => {
    const trimmed = query.trim();
    if (!trimmed) {
      setSearchItems(null);
      void refetch();
      return;
    }
    const result = await search({ query: trimmed, gameSlug, n_results: 20 });
    if ("data" in result && result.data) {
      setSearchItems(result.data.items as MemoryItem[]);
      return;
    }
    dispatch(showNotice(`Memory search failed: ${formatApiError(result.error)}`));
  };

  const onClose = () => dispatch(setMemoryBrowserOpen(false));

  const onAdd = async () => {
    const text = draft.trim();
    if (!text) return;
    const result = await writeItem({
      document: text,
      game_slug: gameSlug,
      kind: "manual",
      session_id: sessionId ?? undefined,
    });
    if ("data" in result && result.data?.written) {
      dispatch(showNotice("Memory saved for future sessions."));
      setDraft("");
      setSearchItems(null);
      void refetch();
      return;
    }
    dispatch(showNotice(`Could not save memory: ${formatApiError(result.error)}`));
  };

  const onDelete = async (id: string) => {
    const result = await deleteItems({ ids: [id] });
    if ("data" in result && result.data) {
      setSearchItems((prev) => (prev ? prev.filter((row) => row.id !== id) : null));
      void refetch();
      return;
    }
    dispatch(showNotice(`Delete failed: ${formatApiError(result.error)}`));
  };

  const busy = browsing || searching || writing || deleting;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      aria-labelledby="memory-browser-title"
      maxWidth="md"
      fullWidth
      slotProps={{
        transition: {
          onEntered: () => {
            setSearchItems(null);
            void refetch();
          },
        },
      }}
    >
      <DialogTitle id="memory-browser-title">Memory Browser</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 0.5 }}>
          <Typography variant="body2" color="text.secondary">
            Persisted learnings from ended sessions live in Chroma ({chromaState}). Prior hits are seeded into
            new sessions on start so agents can reuse play lessons.
          </Typography>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
            <TextField
              size="small"
              label="Game slug"
              value={gameSlug}
              onChange={(e) => {
                setGameSlug(e.target.value);
                setSearchItems(null);
              }}
              sx={{ width: { sm: 140 } }}
            />
            <TextField
              size="small"
              label="Search memories"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
              }}
              fullWidth
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  void runSearch();
                }
              }}
            />
            <Button variant="outlined" disabled={busy} onClick={() => void runSearch()}>
              Search
            </Button>
            <Button
              variant="text"
              disabled={busy}
              onClick={() => {
                setSearchItems(null);
                void refetch();
              }}
            >
              Refresh
            </Button>
          </Stack>
          <Stack spacing={1}>
            {items.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No memories yet. Stop a learn-and-play session to persist blackboard discoveries and lessons,
                or add one manually below.
              </Typography>
            ) : (
              items.map((item) => {
                const meta = item.metadata ?? {};
                const kind = typeof meta.kind === "string" ? meta.kind : "memory";
                const outcome = typeof meta.outcome === "string" ? meta.outcome : null;
                return (
                  <Stack
                    key={item.id}
                    direction="row"
                    spacing={1}
                    alignItems="flex-start"
                    sx={{
                      border: "1px solid",
                      borderColor: "divider",
                      borderRadius: 1,
                      p: 1.25,
                    }}
                  >
                    <Stack spacing={0.5} sx={{ flex: 1, minWidth: 0 }}>
                      <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                        <Chip size="small" label={kind} />
                        {outcome ? <Chip size="small" variant="outlined" label={outcome} /> : null}
                        {typeof meta.game_slug === "string" ? (
                          <Chip size="small" variant="outlined" label={meta.game_slug} />
                        ) : null}
                      </Stack>
                      <Typography variant="body2">{item.document ?? item.id}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {item.id}
                      </Typography>
                    </Stack>
                    <IconButton
                      aria-label="Delete memory"
                      size="small"
                      disabled={busy}
                      onClick={() => {
                        void onDelete(item.id);
                      }}
                    >
                      <DeleteOutlineIcon fontSize="small" />
                    </IconButton>
                  </Stack>
                );
              })
            )}
          </Stack>
          <TextField
            label="Add knowledge"
            placeholder="e.g. KSP: pitch to 45° before circularizing under 80 km."
            multiline
            minRows={2}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
            }}
            fullWidth
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
        <Button variant="contained" disabled={busy || !draft.trim()} onClick={() => void onAdd()}>
          Save memory
        </Button>
      </DialogActions>
    </Dialog>
  );
}
