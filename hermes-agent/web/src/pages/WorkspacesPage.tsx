import { useEffect, useState } from "react";
import { CheckCircle2, GitBranch, HardDrive, RefreshCw, ShieldCheck, Wrench } from "lucide-react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";
import { Input } from "@nous-research/ui/ui/components/input";
import { Label } from "@nous-research/ui/ui/components/label";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { Toast } from "@nous-research/ui/ui/components/toast";
import { useToast } from "@nous-research/ui/hooks/use-toast";
import { api, type BitbucketWorkspace } from "@/lib/api";
import { errorMessage } from "@/lib/api-error";
import { usePageHeader } from "@/contexts/usePageHeader";

const EMPTY: BitbucketWorkspace = {
  configured: false,
  token_saved: false,
  repository_url: "",
  branch: "main",
  username: "x-token-auth",
  commit_name: "",
  commit_email: "",
  workspace_path: "",
  workspace_ready: false,
  vulcan_runtime: "embedded-python3.13",
};

export default function WorkspacesPage() {
  const [state, setState] = useState<BitbucketWorkspace>(EMPTY);
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const { toast, showToast } = useToast();
  const { setTitle } = usePageHeader();

  useEffect(() => {
    setTitle("Repository workspace");
    return () => setTitle(null);
  }, [setTitle]);

  useEffect(() => {
    api.getBitbucketWorkspace()
      .then(setState)
      .catch((error) => showToast(`Could not load workspace: ${errorMessage(error)}`, "error"))
      .finally(() => setLoading(false));
  }, [showToast]);

  const update = (key: keyof BitbucketWorkspace, value: string) =>
    setState((current) => ({ ...current, [key]: value }));

  const save = async () => {
    setSaving(true);
    try {
      const next = await api.saveBitbucketWorkspace({
        repository_url: state.repository_url,
        branch: state.branch,
        token,
        username: state.username,
        commit_name: state.commit_name,
        commit_email: state.commit_email,
        prepare_workspace: true,
      });
      setState(next);
      setToken("");
      showToast("Bitbucket connected and repository workspace prepared.", "success");
    } catch (error) {
      showToast(errorMessage(error), "error");
    } finally {
      setSaving(false);
    }
  };

  const sync = async () => {
    setSyncing(true);
    try {
      setState(await api.syncBitbucketWorkspace());
      showToast("Fetched the configured branch without changing local edits.", "success");
    } catch (error) {
      showToast(errorMessage(error), "error");
    } finally {
      setSyncing(false);
    }
  };

  if (loading) return <div className="flex min-h-48 items-center justify-center"><Spinner /></div>;

  return (
    <div className="mx-auto grid w-full max-w-5xl gap-5 pb-8">
      <Toast toast={toast} />
      <div className="grid gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={state.workspace_ready ? "success" : "outline"}>{state.workspace_ready ? "Workspace ready" : "Not connected"}</Badge>
          <Badge tone={state.token_saved ? "success" : "warning"}>{state.token_saved ? "Token saved securely" : "Token required"}</Badge>
        </div>
        <p className="max-w-3xl text-sm text-muted-foreground">Connect one private Bitbucket repository to Botsky's persistent DataOS disk. The agent can edit and test files, but it must ask before committing or pushing.</p>
      </div>

      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle className="flex items-center gap-2 text-base"><GitBranch className="h-4 w-4" /> Bitbucket repository</CardTitle>
          <CardDescription>The token is validated with Bitbucket, stored in the owner-only profile, and never returned to this page.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5 pt-5">
          <div className="grid gap-2"><Label htmlFor="repository-url">Repository HTTPS URL</Label><Input id="repository-url" value={state.repository_url} onChange={(event) => update("repository_url", event.target.value)} placeholder="https://bitbucket.org/workspace/repository.git" autoComplete="off" /></div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="grid gap-2"><Label htmlFor="repository-branch">Branch</Label><Input id="repository-branch" value={state.branch} onChange={(event) => update("branch", event.target.value)} placeholder="main" autoComplete="off" /></div>
            <div className="grid gap-2"><Label htmlFor="repository-username">Bitbucket username</Label><Input id="repository-username" value={state.username} onChange={(event) => update("username", event.target.value)} placeholder="x-token-auth" autoComplete="username" /><p className="text-xs text-muted-foreground">Use <code>x-token-auth</code> for a repository access token, or your Bitbucket username for an API token/app password.</p></div>
          </div>
          <div className="grid gap-2"><Label htmlFor="repository-token">Repository token</Label><Input id="repository-token" type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder={state.token_saved ? "Saved token retained — enter only to replace" : "Enter repository access token"} autoComplete="new-password" /></div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="grid gap-2"><Label htmlFor="commit-name">Commit author name (optional)</Label><Input id="commit-name" value={state.commit_name} onChange={(event) => update("commit_name", event.target.value)} placeholder="Akshay Chame" /></div>
            <div className="grid gap-2"><Label htmlFor="commit-email">Commit author email (optional)</Label><Input id="commit-email" type="email" value={state.commit_email} onChange={(event) => update("commit_email", event.target.value)} placeholder="you@example.com" /></div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={save} disabled={saving || !state.repository_url || !state.branch} prefix={saving ? <Spinner /> : <ShieldCheck />}>{saving ? "Testing & preparing…" : "Save, test & prepare"}</Button>
            {state.configured && <Button outlined onClick={sync} disabled={syncing} prefix={syncing ? <Spinner /> : <RefreshCw />}>{syncing ? "Fetching…" : "Fetch branch"}</Button>}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card><CardHeader><CardTitle className="flex items-center gap-2 text-base"><HardDrive className="h-4 w-4" /> Persistent workspace</CardTitle></CardHeader><CardContent className="grid gap-2 text-sm"><p className="break-all font-mono text-xs">{state.workspace_path || "$HERMES_HOME/workspace/repos/<repository>"}</p><p className="text-muted-foreground">Files, Git history, agent sessions and generated artifacts survive Service restarts on the 10 GiB DataOS disk.</p></CardContent></Card>
        <Card><CardHeader><CardTitle className="flex items-center gap-2 text-base"><Wrench className="h-4 w-4" /> Vulcan validation</CardTitle></CardHeader><CardContent className="grid gap-2 text-sm"><div className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-success" /><code>vulcan</code> → isolated Python runtime</div><p className="text-muted-foreground">Vulcan uses its pinned Python 3.13 environment while Hermes stays on its own Python runtime. Run commands from the connected repository workspace.</p></CardContent></Card>
      </div>
    </div>
  );
}
