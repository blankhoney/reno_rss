"use client";

import { AnimatePresence } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { DEFAULT_SCORING_SETTINGS, type ScoringSettings } from "@/lib/scoring/settings";
import { AnimatedPanel } from "./AnimatedPanel";
import { useDismissableLayer } from "./useDismissableLayer";

export function ScoringSettingsPanel({
  initialSettings = DEFAULT_SCORING_SETTINGS,
  onSettingsLoaded,
  onSettingsSaved,
}: {
  initialSettings?: ScoringSettings;
  onSettingsLoaded?: (settings: ScoringSettings) => void;
  onSettingsSaved?: (settings: ScoringSettings) => void;
}) {
  const [open, setOpen] = useState(false);
  const [settings, setSettings] = useState<ScoringSettings>(initialSettings);
  const [message, setMessage] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);

  useDismissableLayer({
    enabled: open,
    layerRef: panelRef,
    onDismiss: () => setOpen(false),
  });

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    fetch("/api/scoring/settings", { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("settings_fetch_failed");
        return response.json() as Promise<{ settings: ScoringSettings }>;
      })
      .then((body) => {
        if (!cancelled) {
          setSettings(body.settings);
          onSettingsLoaded?.(body.settings);
        }
      })
      .catch(() => {
        if (!cancelled) setMessage("读取设置失败");
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  async function saveSettings() {
    setIsSaving(true);
    setMessage(null);
    try {
      const response = await fetch("/api/scoring/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      if (!response.ok) throw new Error("settings_save_failed");
      const body = (await response.json()) as { settings: ScoringSettings };
      setSettings(body.settings);
      onSettingsSaved?.(body.settings);
      setMessage("已保存");
    } catch {
      setMessage("保存失败");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="settingsPanel" ref={panelRef}>
      <button type="button" className="readerToolbarBtn" onClick={() => setOpen((v) => !v)}>
        评分设置
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <AnimatedPanel
            key="settings-popover"
            variant="popover"
            className="settingsPopover"
            role="group"
            aria-label="评分设置"
          >
            <label className="settingsRow">
              <input
                type="checkbox"
                checked={settings.autoScoreNewUnread}
                onChange={(event) =>
                  setSettings((current) => ({
                    ...current,
                    autoScoreNewUnread: event.target.checked,
                  }))
                }
              />
              新未读自动评分
            </label>
            <label className="settingsRow">
              <span>每次新文章上限</span>
              <input
                className="settingsNumber"
                type="number"
                min={1}
                max={100}
                value={settings.webhookMaxEntries}
                onChange={(event) =>
                  setSettings((current) => ({
                    ...current,
                    webhookMaxEntries: Number(event.target.value),
                  }))
                }
              />
            </label>
            <label className="settingsRow">
              <span>手动重评篇数</span>
              <input
                className="settingsNumber"
                type="number"
                min={1}
                max={50}
                value={settings.manualBatchSize}
                onChange={(event) =>
                  setSettings((current) => ({
                    ...current,
                    manualBatchSize: Number(event.target.value),
                  }))
                }
              />
            </label>
            <label className="settingsRow">
              <input
                type="checkbox"
                checked={settings.manualRescoreEnabled}
                onChange={(event) =>
                  setSettings((current) => ({
                    ...current,
                    manualRescoreEnabled: event.target.checked,
                  }))
                }
              />
              允许手动重评
            </label>
            <div className="settingsActions">
              <button
                type="button"
                className="readerToolbarBtn readerToolbarBtnPrimary"
                disabled={isSaving}
                onClick={() => void saveSettings()}
              >
                {isSaving ? "保存中" : "保存"}
              </button>
              {message ? <span className="settingsMessage">{message}</span> : null}
            </div>
          </AnimatedPanel>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
