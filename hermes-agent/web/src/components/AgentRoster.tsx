import { useEffect, useMemo, useState } from "react";
import { Bot, Plus, Radio } from "lucide-react";
import { useNavigate } from "react-router";
import { cn } from "@/lib/utils";
import { api, type ProfileInfo } from "@/lib/api";
import { useProfileScope } from "@/contexts/useProfileScope";

export function AgentRoster({ collapsed }: { collapsed: boolean }) {
  const navigate = useNavigate();
  const { profile, profiles, setProfile } = useProfileScope();
  const [details, setDetails] = useState<ProfileInfo[]>([]);

  useEffect(() => {
    let cancelled = false;
    void api.getProfiles().then((result) => {
      if (!cancelled) setDetails(result.profiles);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [profiles]);

  const agents = useMemo(() => {
    if (details.length) return details;
    return profiles.map((name) => ({
      name,
      display_name: name,
      gateway_running: false,
    } as ProfileInfo));
  }, [details, profiles]);

  const selectAgent = (name: string) => {
    setProfile(name);
    navigate(`/chat?profile=${encodeURIComponent(name)}`);
  };

  if (collapsed) {
    return (
      <div className="hidden border-b border-current/10 py-2 lg:flex lg:flex-col lg:items-center lg:gap-1">
        {agents.slice(0, 5).map((agent) => (
          <button
            key={agent.name}
            type="button"
            title={agent.display_name || agent.name}
            aria-label={`Open ${agent.display_name || agent.name}`}
            onClick={() => selectAgent(agent.name)}
            className={cn(
              "relative flex h-9 w-9 items-center justify-center rounded-full border transition-colors",
              profile === agent.name
                ? "border-midground bg-midground/10 text-midground"
                : "border-current/15 text-text-secondary hover:text-midground",
            )}
          >
            <Bot className="h-4 w-4" />
            {agent.gateway_running && (
              <span className="absolute bottom-0 right-0 h-2 w-2 rounded-full border border-background-base bg-emerald-400" />
            )}
          </button>
        ))}
        <button
          type="button"
          title="New agent"
          aria-label="New agent"
          onClick={() => navigate("/profiles/new")}
          className="flex h-9 w-9 items-center justify-center rounded-full border border-dashed border-current/25 text-text-secondary hover:border-midground hover:text-midground"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <section className="shrink-0 border-b border-current/10 px-3 py-3">
      <div className="mb-2 flex items-center justify-between px-2">
        <span className="font-sans text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-text-tertiary">
          Agents
        </span>
        <button
          type="button"
          onClick={() => navigate("/profiles/new")}
          className="inline-flex items-center gap-1 text-[0.68rem] font-semibold uppercase tracking-[0.1em] text-text-secondary hover:text-midground"
        >
          <Plus className="h-3 w-3" /> New
        </button>
      </div>

      <div className="max-h-48 space-y-1 overflow-y-auto">
        {agents.map((agent) => {
          const selected = profile === agent.name || (!profile && agent.is_default);
          return (
            <button
              key={agent.name}
              type="button"
              onClick={() => selectAgent(agent.name)}
              className={cn(
                "group flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors",
                selected
                  ? "bg-midground/10 text-midground"
                  : "text-text-secondary hover:bg-current/5 hover:text-midground",
              )}
            >
              <span className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-current/15 bg-background-base">
                <Bot className="h-4 w-4" />
                {agent.gateway_running && (
                  <Radio className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full bg-background-base text-emerald-400" />
                )}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold normal-case tracking-normal">
                  {agent.display_name || agent.name}
                </span>
                <span className="block truncate text-[0.65rem] normal-case tracking-normal text-text-tertiary">
                  {agent.model || agent.description || "DataOS agent"}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
