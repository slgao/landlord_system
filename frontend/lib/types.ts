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
  months_due: number;
  amount_due: number;
  currency: string;
  overdue_months: { month: string; expected: number; paid: number; gap: number }[];
}

export interface BillingProfile {
  id: number;
  tenant_id: number;
  label: string;
  created_date?: string;
  data: any;
}
