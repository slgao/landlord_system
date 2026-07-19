export interface Property {
  id: number;
  name: string;
  address?: string;
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
  };
  werbungskosten: {
    afa: { afa: number; complete: boolean; base?: number; annual?: number; months?: number };
    schuldzinsen: {
      final: number;
      source: "manual" | "computed" | "none";
      computed: { label: string; interest: number; tilgung: number; balance_end: number; monthly_payment: number }[];
    };
    recurring: { cost_type: string; monthly: number; months: number; total: number; deductible: boolean }[];
    recurring_total: number;
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
