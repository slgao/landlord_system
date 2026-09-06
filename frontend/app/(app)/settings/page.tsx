"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import { Config } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SettingsPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState<Config>({});
  const [smtp, setSmtp] = useState({ smtp_host: "", smtp_port: "587", smtp_user: "", smtp_from: "", smtp_password: "" });
  // Whether a password is on file. The API never sends the password itself,
  // so the field stays blank and blank on save means "keep the stored one".
  const [passwordSet, setPasswordSet] = useState(false);
  const [sigUrl, setSigUrl] = useState<string | null>(null);
  // Built in an effect (not during render) so reading localStorage doesn't
  // cause a server/client hydration mismatch on the iframe src.
  const [padSrc, setPadSrc] = useState<string | null>(null);

  const { data: config } = useQuery<Config>({
    queryKey: ["config"],
    queryFn: () => api.get("/api/config/").then((r) => r.data),
  });

  const { data: smtpConfig } = useQuery<{
    smtp_host?: string | null; smtp_port?: string | null; smtp_user?: string | null;
    smtp_from?: string | null; smtp_password_set?: boolean;
  }>({
    queryKey: ["smtp-config"],
    queryFn: () => api.get("/api/config/smtp").then((r) => r.data),
  });

  useEffect(() => {
    const token = localStorage.getItem("token");
    setPadSrc(`${API}/api/signature-pad${token ? `?token=${token}` : ""}`);
  }, []);
  useEffect(() => { if (config) setForm(config); }, [config]);
  useEffect(() => {
    if (!smtpConfig) return;
    const { smtp_password_set, ...rest } = smtpConfig;
    setPasswordSet(!!smtp_password_set);
    // Unset keys come back as null; keep the defaults (port 587) for those.
    setSmtp((f) => ({ ...f, ...Object.fromEntries(Object.entries(rest).filter(([, v]) => v != null)) }));
  }, [smtpConfig]);

  const save = useMutation({
    mutationFn: (data: Config) => api.put("/api/config/", data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["config"] }); toast.success("Settings saved"); },
    onError: (e) => toast.error(errorMessage(e, "Failed to save")),
  });

  const saveSmtp = useMutation({
    mutationFn: (data: typeof smtp) => api.put("/api/config/smtp", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["smtp-config"] });
      setSmtp((f) => ({ ...f, smtp_password: "" }));
      toast.success("SMTP settings saved");
    },
    onError: (e) => toast.error(errorMessage(e, "Failed to save SMTP settings")),
  });

  function field(key: keyof Config, label: string, placeholder = "") {
    return (
      <div className="space-y-1.5">
        <Label>{label}</Label>
        <Input value={form[key] || ""} onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))} placeholder={placeholder} />
      </div>
    );
  }

  function smtpField(key: keyof typeof smtp, label: string, type = "text", placeholder = "") {
    return (
      <div className="space-y-1.5">
        <Label>{label}</Label>
        <Input type={type} value={smtp[key] || ""} onChange={(e) => setSmtp((f) => ({ ...f, [key]: e.target.value }))} placeholder={placeholder} />
      </div>
    );
  }

  function loadSig() {
    const token = localStorage.getItem("token");
    setSigUrl(`${API}/api/signature?t=${Date.now()}&token=${token}`);
  }

  return (
    <div className="max-w-2xl space-y-6">
      <PageHeader title="Settings" />

      {/* Landlord info */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Landlord Information</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {field("landlord_name", "Name / Company", "Max Mustermann")}
          {field("landlord_address", "Address")}
          {field("landlord_iban", "IBAN")}
          {field("landlord_bank", "Bank Name")}
          {field("landlord_email", "Email")}
          <Button onClick={() => save.mutate(form)} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save Settings"}
          </Button>
        </CardContent>
      </Card>

      {/* SMTP config */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Email / SMTP Settings</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-muted-foreground">Used to send payment reminder emails to tenants.</p>
          <div className="grid grid-cols-2 gap-4">
            {smtpField("smtp_host", "SMTP Host", "text", "smtp.gmail.com")}
            {smtpField("smtp_port", "Port", "text", "587")}
          </div>
          {smtpField("smtp_user", "Username / Email")}
          {smtpField("smtp_from", "From Address (shown to tenant)")}
          {smtpField("smtp_password", "Password / App Password", "password",
            passwordSet ? "•••••••• saved — leave blank to keep it" : "")}
          <Button onClick={() => saveSmtp.mutate(smtp)} disabled={saveSmtp.isPending}>
            {saveSmtp.isPending ? "Saving…" : "Save SMTP Settings"}
          </Button>
        </CardContent>
      </Card>

      {/* Signature */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Signature</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">Draw your signature below. It will be used in all generated PDFs.</p>
          {padSrc && <iframe src={padSrc} className="w-full h-48 rounded-md border border-border bg-white" />}
          <Button variant="outline" size="sm" onClick={loadSig}>View saved signature</Button>
          {sigUrl && (
            <div className="p-3 rounded-md border border-border bg-white inline-block">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={sigUrl} alt="Saved signature" className="max-h-16" />
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
