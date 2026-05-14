"use client";

import { useEffect, useState } from "react";

type ScoringSettings = {
  autoScoreNewUnread: boolean;
  webhookMaxEntries: number;
  manualRescoreEnabled: boolean;
};

const DEFAULT_SETTINGS: ScoringSettings = {
  autoScoreNewUnread: true,
  webhookMaxEntries: 20,
  manualRescoreEnabled: true,
};

export function ScoringSettingsPanel() {
  const [open, setOpen] = useState(false);
  const [settings, setSettings] = useState<ScoringSettings>(DEFAULT_SETTINGS);
  const [message, setMessage] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    fetch("/api/scoring/settings", { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("settings_fetch_failed");
        return response.json() as Promise<{ settings: ScoringSettings }>;
      })
      .then((body) => {
        if (!cancelled) setSettings(body.settings);
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
      setMessage("已保存");
    } catch {
      setMessage("保存失败");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="settingsPanel">
      <button type="button" className="readerToolbarBtn" onClick={() => setOpen((v) => !v)}>
        评分设置
      </button>
      {open ? (
        <div className="settingsPopover" role="group" aria-label="评分设置">
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
        </div>
      ) : null}
    </div>
  );
}
