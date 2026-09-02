export interface Building {
  id: number;
  name?: string | null;
  street?: string | null;
  house_no?: string | null;
  zip?: string | null;
  city?: string | null;
  notes?: string | null;
  unit_count: number;
}

export interface Property {
  id: number;
  name: string;
  address?: string;
  building_id?: number | null;
  we_label?: string | null;   // Wohnungseigentum unit label, e.g. "WE 3"
  mea?: number | null;        // Miteigentumsanteil
  building_name?: string | null;
}

export interface Apartment {
  id: number;
  property_id: number;
  property_name?: string;
  name: string;
  flat?: string;
}

export interface Tenant {
  id: number;
  name: string;
  email?: string;
  phone?: string;
  gender: string;
}

export interface Contract {
  id: number;
  tenant_id: number;
  tenant_name?: string;
  apartment_id: number;
  apartment_name?: string;
  property_name?: string;
  rent: number;
  currency: string;
  start_date: string;
  end_date?: string;
  kaution_amount?: number;
  kaution_currency: string;
  kaution_paid_date?: string;
  kaution_returned_date?: string;
  kaution_returned_amount?: number;
  terminated: boolean;
}

export interface CoTenant {
  id: number;
  contract_id: number;
  name: string;
  gender: string;
  email?: string;
  in_contract: boolean;
}

export interface KautionDeduction {
  id: number;
  contract_id: number;
  date: string;
  amount: number;
  category: string;
  reason?: string;
}

export interface KautionPayment {
  id: number;
  contract_id: number;
  date: string;
  amount: number;
  note?: string;
}

/** One repayment of the deposit. A deposit is often released in two steps —
 *  part after the handover, the rest once the Nebenkostenabrechnung is settled —
 *  so this is a ledger, not a single field on the contract. */
export interface KautionReturn {
  id: number;
  contract_id: number;
  date: string;
  amount: number;
  note?: string;
}

export interface Payment {
  id: number;
  contract_id: number;
  tenant_name?: string;
  apartment_name?: string;
  amount: number;          // EUR value that counts as income
  payment_date: string;
  currency?: string;       // always "EUR" for the counted value
  orig_amount?: number | null;    // foreign tender note, if paid in another currency
  orig_currency?: string | null;
}

export interface FlatCost {
  id: number;
  apartment_id: number;
  apartment_name?: string;
  property_name?: string;
  cost_type: string;
  amount: number;
  frequency: string;
  valid_from?: string;
  valid_to?: string;
}

export interface DashboardStats {
  properties: number;
  apartments: number;
  tenants: number;
  contracts: number;
}

export interface ContractAlert {
  tenant_name: string;
  apartment_name: string;
  property_name: string;
  end_date: string;
  days_remaining: number;
  level: "expired" | "warning";
}

export interface StromMeter {
  id: number;
  apartment_id: number;
  apartment_name?: string;
  serial_number?: string;
  description?: string;
  scope: string;
}

export interface GasMeter {
  id: number;
  apartment_id: number;
  apartment_name?: string;
  serial_number?: string;
  description?: string;
  z_zahl: number;
  brennwert: number;
  scope: string;
}

export interface WasserMeter {
  id: number;
  apartment_id: number;
  apartment_name?: string;
  serial_number?: string;
  description?: string;
  type: string;
  scope: string;
}

export interface HeizungMeter {
  id: number;
  apartment_id: number;
  apartment_name?: string;
  serial_number?: string;
  description?: string;
  unit_price: number;
  unit_label: string;
  conversion_factor: number;
  scope: string;
}

export interface MeterReading {
  id: number;
  meter_type: string;
  meter_id: number;
  reading_date: string;
  reading: number;
  note?: string;
  // Set when the reading was taken at a handover. The reading is a normal
  // reading either way — this only records where it came from.
  protocol_id?: number | null;
}

// ── Übergabeprotokoll ────────────────────────────────────────────────────────

export type ProtocolKind = "move_in" | "move_out";
export type ItemCondition = "ok" | "wear" | "defect";

export interface HandoverProtocol {
  id: number;
  contract_id: number;
  kind: ProtocolKind;
  date: string;
  time?: string | null;
  present_persons?: string | null;
  note?: string | null;
  signed: boolean;
  // Rolled up by the API so the contract page can summarise without
  // fetching every item of every protocol.
  item_count: number;
  defect_count: number;
  defect_cost: number;
  reading_count: number;
}

export interface ProtocolItem {
  id: number;
  protocol_id: number;
  kind: "condition" | "key";
  area?: string | null;
  condition?: ItemCondition | null;
  quantity?: number | null;
  estimated_cost?: number | null;
  note?: string | null;
  sort_order: number;
}

// One meter a given room should be read for. Comes from /meters/for-apartment,
// which resolves the WG rule server-side: the flat's shared meters plus this
// room's own room-scoped ones (a Heizkostenverteiler).
export interface ApartmentMeter {
  meter_type: "strom" | "gas" | "wasser" | "heizung";
  id: number;
  apartment_id: number;
  apartment_name?: string | null;
  serial_number?: string | null;
  description?: string | null;
  scope: string;
  // False when registered on a flatmate's room rather than this one.
  own: boolean;
}

export interface ProtocolReading {
  id: number;
  meter_type: string;
  meter_id: number;
  reading_date: string;
  reading: number;
  note?: string | null;
  serial_number?: string | null;
  description?: string | null;
}

export interface Config {
  landlord_name?: string;
  landlord_address?: string;
  landlord_iban?: string;
  landlord_bank?: string;
  landlord_email?: string;
}

export interface PaymentReminder {
  contract_id: number;
  tenant_name: string;
  tenant_email: string;
  apartment_name: string;
  property_name: string;
  currency: string;
  rent: number;
  settled_until: string | null;
  months_due: number;
  amount_due: number;
  balance: number;
  expected_total: number;
  paid_total: number;
  current_month_paid: number;
  first_month: string | null;
  last_month: string | null;
  months: { month: string; expected: number; paid: number; balance_after: number }[];
}

export interface BillingProfile {
  id: number;
  tenant_id: number;
  label: string;
  created_date?: string;
  data: any;
}

export interface RagCitation {
  law_ref: string | null;
  section: string | null;
  score: number;
}

export interface RagAnswer {
  answer: string;
  citations: RagCitation[];
  latency_ms: number;
  refused: boolean;
}

// Agentic assistant (POST /api/assistant/ask). Unlike RagAnswer this answers
// over the landlord's own portfolio AND the legal corpus; `tools_consulted`
// lists which tools the agent called (R7 transparency), and `thread_id` ties
// follow-up questions to the same conversation (R4 multi-turn).
export interface AssistantAnswer {
  answer: string;
  tools_consulted: string[];
  thread_id: number;
}

// ── Tax module (Anlage V helper) ──────────────────────────────────────────

export interface Mortgage {
  id: number;
  property_id: number;
  label: string | null;
  principal: number;
  interest_rate_pct: number;
  tilgung_rate_pct: number;
  start_date: string;
  note: string | null;
}

export interface TaxProfile {
  property_id: number;
  property_name: string;
  tax_relevant: boolean;
  purchase_date: string | null;
  purchase_price: number | null;
  building_share_pct: number | null;
  afa_rate_pct: number | null;
  notes: string | null;
  mortgages: Mortgage[];
  afa_annual: number | null;
}

export interface TaxExpense {
  id: number;
  property_id: number;
  property_name: string;
  apartment_id: number | null;
  expense_date: string;
  amount: number;
  category: string;
  vendor: string | null;
  note: string | null;
  deductible: number;
  distribute_years: number;
  source_file: string | null;
}

export interface NkSplit {
  contract_id: number;
  tenant_name: string;
  apartment_name: string;
  property_id: number;
  property_name: string;
  rent: number;
  nebenkosten_vorauszahlung: number | null;
  kaltmiete: number | null;
  start_date: string;
  end_date: string | null;
}

export interface TaxReportProperty {
  property_id: number;
  property_name: string;
  income: {
    final: number;
    source: "payments" | "estimate" | "override";
    payments_total: number;
    payments_count: number;
    estimate_total: number;
    estimate_rows: { tenant: string; months: number; rent: number; total: number }[];
    override_note: string | null;
    nk_known: boolean;
    umlagen: number | null;
    kaltmiete: number | null;
    split_source: "contracts" | "override" | null;
  };
  werbungskosten: {
    afa: { afa: number; complete: boolean; source: "computed" | "override" | "incomplete"; computed_afa?: number; base?: number; annual?: number; months?: number; items?: { label: string; amount: number }[] };
    schuldzinsen: {
      final: number;
      source: "manual" | "computed" | "none" | "override";
      computed: { label: string; interest: number; tilgung: number; balance_end: number; monthly_payment: number }[];
    };
    recurring: { cost_type: string; monthly: number; months: number; total: number; deductible: boolean }[];
    recurring_total: number;
    recurring_computed: number;
    recurring_source: "computed" | "override";
    one_off: (TaxExpense & { share_this_year: number })[];
    one_off_total: number;
    total: number;
  };
  result: number;
}

export interface TaxReport {
  year: number;
  properties: TaxReportProperty[];
  excluded_properties: string[];
  totals: { income: number; werbungskosten: number; result: number };
}

// ── Financing (Zins/Tilgung development) ─────────────────────────────────────

export interface AmortRow {
  year: number;
  interest: number;      // Zins paid within this year
  tilgung: number;       // principal repaid within this year
  payment: number;       // interest + tilgung — the annuity paid this year
  balance_end: number;   // Restschuld once December is booked
  interest_cum: number;  // both cumulative since the loan started
  tilgung_cum: number;
  months?: number;       // present per loan, absent on merged timelines
}

export interface AmortMortgage {
  id: number;
  property_id: number;
  label: string | null;
  principal: number;
  interest_rate_pct: number;
  tilgung_rate_pct: number;
  start_date: string;
  note: string | null;
  schedule: AmortRow[];
  paid_off_year: number;
  interest_lifetime: number;
  balance_now: number;
  interest_since_start: number;
  tilgung_since_start: number;
  monthly_payment: number;
}

export interface AmortProperty {
  property_id: number;
  property_name: string;
  apartments: string[];
  mortgages: AmortMortgage[];
  combined: AmortRow[];
  principal_total: number;
  balance_now: number;
  interest_since_start: number;
  tilgung_since_start: number;
  interest_lifetime: number;
  monthly_payment: number;
  paid_off_year: number;
}

export interface Amortization {
  as_of: string;
  properties: AmortProperty[];
  totals: (Omit<AmortProperty, "property_id" | "property_name" | "apartments" | "mortgages"> & {
    combined: AmortRow[];
  }) | null;
}
