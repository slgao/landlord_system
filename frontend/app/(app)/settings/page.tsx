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
import { Download } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SettingsPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState<Config>({});
  const [smtp, setSmtp] = useState({ smtp_host: "", smtp_port: "587", smtp_user: "", smtp_from: "", smtp_password: "" });
  // Whether a password is on file. The API never sends the password itself,
  // so the field stays blank and blank on save means "keep the stored one".
  const [passwordSet, setPasswordSet] = useState(false);
  const [sigUrl, setSigUrl] = useState<string | null>(null);
  // The pad's markup, fetched with a normal authenticated request and mounted
  // with srcDoc. It used to be an iframe src carrying ?token=<session JWT>,
  // which uvicorn writes into its access log in full.
  const [padHtml, setPadHtml] = useState<string | null>(null);

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
    let cancelled = false;
    api.get("/api/signature-pad", { responseType: "text" })
      .then((r) => {
        if (cancelled) return;
        const token = localStorage.getItem("token") ?? "";
        // The token lives in the document, not in a URL. API_BASE has to be
        // absolute: under srcDoc a relative path resolves against this origin.
        setPadHtml(String(r.data)
          .replace("__SIG_TOKEN__", token)
          .replace("__API_BASE__", API));
      })
      .catch(() => { if (!cancelled) toast.error("Could not load the signature pad"); });
    return () => { cancelled = true; };
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

  // The label is tied to its field by id. Without that the two are only near
  // each other on screen: a screen reader announces the input as unlabelled,
  // and clicking the label does not focus it.
  function field(key: keyof Config, label: string, placeholder = "") {
    const id = `cfg-${String(key)}`;
    return (
      <div className="space-y-1.5">
        <Label htmlFor={id}>{label}</Label>
        <Input id={id} name={String(key)} value={form[key] || ""}
          onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
          placeholder={placeholder} />
      </div>
    );
  }

  function smtpField(key: keyof typeof smtp, label: string, type = "text", placeholder = "") {
    const id = `smtp-${String(key)}`;
    return (
      <div className="space-y-1.5">
        <Label htmlFor={id}>{label}</Label>
        <Input id={id} name={String(key)} type={type} value={smtp[key] || ""}
          onChange={(e) => setSmtp((f) => ({ ...f, [key]: e.target.value }))}
          placeholder={placeholder}
          autoComplete={type === "password" ? "new-password" : undefined} />
      </div>
    );
  }

  const { data: summary } = useQuery<{ tables: Record<string, number>; rows: number }>({
    queryKey: ["export-summary"],
    queryFn: () => api.get("/api/export/summary").then((r) => r.data),
  });
  const [exporting, setExporting] = useState(false);

  async function downloadExport() {
    setExporting(true);
    try {
      // A blob, not a link to the endpoint: the file needs the Authorization
      // header, which a plain <a href> cannot carry.
      const res = await api.get("/api/export/", { responseType: "blob" });
      const url = URL.createObjectURL(res.data as Blob);
      const a = document.createElement("a");
      const stamp = new Date().toISOString().slice(0, 10);
      a.href = url;
      a.download = `dachly-export-${stamp}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Downloaded");
    } catch (e) {
      toast.error(errorMessage(e, "Could not prepare the export"));
    } finally {
      setExporting(false);
    }
  }

  // Fetched as a blob and shown from an object URL, so the <img> needs no
  // credentials of its own and no token ends up in a URL.
  async function loadSig() {
    try {
      const res = await api.get("/api/signature", { responseType: "blob" });
      setSigUrl((old) => { if (old) URL.revokeObjectURL(old); return URL.createObjectURL(res.data); });
    } catch (e) {
      const status = (e as { response?: { status?: number } })?.response?.status;
      toast.error(status === 404 ? "No signature saved yet" : errorMessage(e, "Could not load the signature"));
    }
  }
  // Release the object URL when the page goes away.
  useEffect(() => () => { if (sigUrl) URL.revokeObjectURL(sigUrl); }, [sigUrl]);

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
          {padHtml
            ? <iframe srcDoc={padHtml} title="Signature pad"
                className="w-full h-48 rounded-md border border-border bg-white" />
            : <p className="text-xs text-muted-foreground">Loading the pad…</p>}
          <Button variant="outline" size="sm" onClick={loadSig}>View saved signature</Button>
          {sigUrl && (
            <div className="p-3 rounded-md border border-border bg-white inline-block">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={sigUrl} alt="Saved signature" className="max-h-16" />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Export */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Your data</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Everything you have entered, as one JSON file: properties, flats,
            tenancies and every agreed rent, payments, costs, Kaution movements,
            meter readings and the tax figures. §147 AO wants the records behind
            a return readable for ten years, which is longer than any one
            application lasts.
          </p>
          {summary && (
            <p className="text-xs text-muted-foreground tabular-nums">
              {summary.rows.toLocaleString("de-DE")} rows across{" "}
              {Object.values(summary.tables).filter((n) => n > 0).length} tables.
            </p>
          )}
          <Button variant="outline" size="sm" onClick={downloadExport}
            disabled={exporting}>
            <Download className="size-4 mr-1" />
            {exporting ? "Preparing…" : "Download everything"}
          </Button>
          <p className="text-xs text-muted-foreground">
            Stored PDFs are not included — each has its own download, and the
            rows that have one say so. These settings are left out too, because
            the SMTP password is encrypted with a key the file does not carry.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
