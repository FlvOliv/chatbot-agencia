"use client";

import { useEffect, useState } from "react";

import type { ConversationDetail, LeadDetail, Tag } from "@/lib/types";
import { ConversaView } from "./conversa-view";
import { LeadPanel } from "./lead-panel";

export function ConversaWorkspace({
  conv,
  initialPaused,
  lead,
  allTags = [],
  currentTags = [],
}: {
  conv: ConversationDetail;
  initialPaused: boolean;
  lead: LeadDetail | null;
  allTags?: Tag[];
  currentTags?: Tag[];
}) {
  const [showLead, setShowLead] = useState(true);

  useEffect(() => {
    const saved = localStorage.getItem("malu:showLead");
    if (saved !== null) setShowLead(saved === "1");
  }, []);

  function toggle() {
    setShowLead((v) => {
      const next = !v;
      try {
        localStorage.setItem("malu:showLead", next ? "1" : "0");
      } catch {
        /* ignora */
      }
      return next;
    });
  }

  return (
    <>
      <div className="min-w-0 flex-1">
        <ConversaView
          conv={conv}
          initialPaused={initialPaused}
          onToggleLead={toggle}
          leadOpen={showLead}
          allTags={allTags}
          currentTags={currentTags}
        />
      </div>
      {showLead ? (
        <aside className="hidden w-[300px] shrink-0 flex-col overflow-y-auto border-l border-border lg:flex">
          <LeadPanel lead={lead} />
        </aside>
      ) : null}
    </>
  );
}
