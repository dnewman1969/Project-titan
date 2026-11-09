import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useState } from "react";

import {
  useApproveUploadJobMutation,
  useConnectYoutubeStubMutation,
  useCreateUploadJobMutation,
  useDisconnectYoutubeStubMutation,
  useGetYoutubeAccountQuery,
  useListUploadJobsQuery,
  useStubUploadJobMutation,
} from "../../app/api";
import { formatApiError } from "../../app/formatApiError";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { setPublishOpen, showNotice } from "../operations/layoutSlice";

/** Ops Center control for YouTube stub auth + private-first draft uploads. */
export function YouTubePublishDialog() {
  const dispatch = useAppDispatch();
  const open = useAppSelector((s) => s.layout.publishOpen);
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const sessionTitle = useAppSelector((s) => s.sessions.activeTitle);
  const [title, setTitle] = useState("");
  const { data: account, refetch: refetchAccount } = useGetYoutubeAccountQuery(undefined, {
    skip: !open,
    pollingInterval: open ? 8000 : 0,
  });
  const { data: jobs, refetch: refetchJobs } = useListUploadJobsQuery(
    { limit: 8 },
    { skip: !open, pollingInterval: open ? 5000 : 0 },
  );
  const [connect, { isLoading: connecting }] = useConnectYoutubeStubMutation();
  const [disconnect, { isLoading: disconnecting }] = useDisconnectYoutubeStubMutation();
  const [createJob, { isLoading: creating }] = useCreateUploadJobMutation();
  const [approveJob, { isLoading: approving }] = useApproveUploadJobMutation();
  const [uploadJob, { isLoading: uploading }] = useStubUploadJobMutation();

  const connected = account?.connected === true;
  const channelName = account?.account != null ? account.account.display_name : "stub";
  const draftTitle = title.trim() || sessionTitle?.trim() || "Titan session draft";

  const onClose = () => dispatch(setPublishOpen(false));

  const onConnect = async () => {
    const result = await connect(undefined);
    if ("data" in result && result.data) {
      dispatch(showNotice(result.data.message ?? "YouTube stub connected."));
      void refetchAccount();
      return;
    }
    dispatch(showNotice(`Connect failed: ${formatApiError(result.error)}`));
  };

  const onDisconnect = async () => {
    const result = await disconnect(undefined);
    if ("data" in result && result.data) {
      dispatch(showNotice(result.data.message ?? "YouTube stub disconnected."));
      void refetchAccount();
      return;
    }
    dispatch(showNotice(`Disconnect failed: ${formatApiError(result.error)}`));
  };

  const onCreateDraft = async () => {
    const result = await createJob({
      title: draftTitle,
      privacy: "private",
      ...(sessionId ? { session_id: sessionId } : {}),
    });
    if ("data" in result && result.data) {
      dispatch(showNotice(`Draft upload ready (${result.data.status}).`));
      setTitle("");
      void refetchJobs();
      return;
    }
    dispatch(showNotice(`Draft failed: ${formatApiError(result.error)}`));
  };

  const onApprove = async (jobId: string) => {
    const result = await approveJob(jobId);
    if ("data" in result && result.data) {
      dispatch(showNotice("Draft approved — run stub upload when ready."));
      void refetchJobs();
      return;
    }
    dispatch(showNotice(`Approve failed: ${formatApiError(result.error)}`));
  };

  const onUpload = async (jobId: string) => {
    const result = await uploadJob(jobId);
    if ("data" in result && result.data) {
      dispatch(
        showNotice(
          result.data.remote_url ? `Stub published: ${result.data.remote_url}` : "Stub upload finished.",
        ),
      );
      void refetchJobs();
      return;
    }
    dispatch(showNotice(`Upload failed: ${formatApiError(result.error)}`));
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm" aria-labelledby="youtube-publish-title">
      <DialogTitle id="youtube-publish-title">YouTube publish (stub)</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 0.5 }}>
          <Typography variant="body2" color="text.secondary">
            Beta placeholder: no Google OAuth. Connect stub auth, create a private draft, approve, then run
            the stub uploader (fake Studio URL).
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="body2" sx={{ flex: 1 }}>
              {connected ? `Connected: ${channelName}` : "Not connected"}
            </Typography>
            {connected ? (
              <Button
                size="small"
                onClick={() => {
                  void onDisconnect();
                }}
                disabled={disconnecting}
              >
                Disconnect
              </Button>
            ) : (
              <Button
                size="small"
                variant="contained"
                onClick={() => {
                  void onConnect();
                }}
                disabled={connecting}
              >
                Connect stub
              </Button>
            )}
          </Stack>
          <TextField
            label="Draft title"
            size="small"
            value={title}
            onChange={(e) => {
              setTitle(e.target.value);
            }}
            placeholder={draftTitle}
            fullWidth
          />
          <Button
            variant="contained"
            onClick={() => {
              void onCreateDraft();
            }}
            disabled={!connected || creating}
          >
            Create private draft
          </Button>
          <Stack spacing={1}>
            <Typography variant="caption" color="text.secondary">
              Recent upload jobs
            </Typography>
            {(jobs?.items ?? []).length === 0 ? (
              <Typography variant="body2" color="text.disabled">
                No drafts yet.
              </Typography>
            ) : (
              (jobs?.items ?? []).map((job) => (
                <Stack
                  key={job.id}
                  direction="row"
                  spacing={1}
                  alignItems="center"
                  sx={{ borderBottom: 1, borderColor: "divider", pb: 1 }}
                >
                  <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }} noWrap>
                    {job.title ?? "Draft"} · {job.status} · {job.privacy}
                  </Typography>
                  {job.status === "awaiting_approval" ? (
                    <Button
                      size="small"
                      onClick={() => {
                        void onApprove(job.id);
                      }}
                      disabled={approving}
                    >
                      Approve
                    </Button>
                  ) : null}
                  {job.status === "approved" ? (
                    <Button
                      size="small"
                      variant="contained"
                      onClick={() => {
                        void onUpload(job.id);
                      }}
                      disabled={uploading}
                    >
                      Stub upload
                    </Button>
                  ) : null}
                </Stack>
              ))
            )}
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
