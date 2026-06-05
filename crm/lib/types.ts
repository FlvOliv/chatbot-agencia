export type LeadTemp = "frio" | "morno" | "quente" | "urgente";

export type HealthStatus = "ok" | "degraded" | "down";

export interface ClienteOut {
  phone: string;
  profile_name: string | null;
  name: string | null;
  created_at: string;
}

export interface LeadOut {
  id: string;
  phone: string;
  name: string | null;
  destination: string | null;
  travel_type: string | null;
  lead_temp: LeadTemp | null;
  briefing_md: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeadListItem {
  id: string;
  phone: string;
  name: string | null;
  destination: string | null;
  lead_temp: LeadTemp | null;
  created_at: string;
}

export interface LeadListResponse {
  items: LeadListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface LeadDetail {
  lead: LeadOut;
  cliente: ClienteOut | null;
  conversation_count: number;
}

export interface MessageOut {
  id: string;
  phone: string;
  role: "user" | "assistant";
  content: string;
  model_used: string | null;
  created_at: string;
}

export interface ConversationDetail {
  phone: string;
  customer_name: string | null;
  messages: MessageOut[];
}

export interface DashboardMetrics {
  leads_today: number;
  leads_week: number;
  active_conversations: number;
  pending_for_lu: number;
  reservas_ativas: number;
  by_temperature: Record<LeadTemp, number>;
}

export interface DailyCount {
  date: string;
  count: number;
}

export interface TopDestination {
  destination: string;
  count: number;
  pct: number;
}

export interface HourlyBucket {
  hour: number;
  count: number;
}

export interface ConversionRate {
  conversations_started: number;
  leads_generated: number;
  rate: number;
}

export interface AIProviderBreakdown {
  gemini: number;
  groq: number;
  unknown: number;
}

export interface DashboardInsights {
  range_days: number;
  generated_at: string;
  conversations_per_day: DailyCount[];
  leads_per_day: DailyCount[];
  top_destinations: TopDestination[];
  hourly_distribution: HourlyBucket[];
  conversion_rate: ConversionRate;
  ai_provider_breakdown: AIProviderBreakdown;
}
