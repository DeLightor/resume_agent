export type ApplicationStatus =
  | 'draft' | 'applied' | 'hr_screen' | 'interview' | 'offer' | 'rejected' | 'withdrawn';

export interface ApplicationEvent {
  id: number;
  event_type: 'created' | 'status_changed' | 'updated' | 'deleted' | 'restored';
  from_status: ApplicationStatus | null;
  to_status: ApplicationStatus | null;
  note: string | null;
  changed_fields: string[];
  created_at: string;
}

export interface ApplicationRecord {
  id: string;
  resume_node_id: string;
  resume_node_title: string;
  source_node_deleted: boolean;
  resume_version: number;
  resume_snapshot: Record<string, unknown>;
  company: string;
  role: string;
  job_url: string | null;
  jd_snapshot: Record<string, unknown> | null;
  status: ApplicationStatus;
  next_action: string | null;
  follow_up_at: string | null;
  notes: string | null;
  version: number;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
  is_overdue: boolean;
}

export interface ApplicationDetail extends ApplicationRecord { events: ApplicationEvent[]; }

export interface CreateApplicationRequest {
  resume_node_id: string;
  company: string;
  role: string;
  job_url?: string | null;
  jd_snapshot?: Record<string, unknown> | null;
  status?: ApplicationStatus;
  next_action?: string | null;
  follow_up_at?: string | null;
  notes?: string | null;
}

export interface UpdateApplicationRequest {
  expected_version: number;
  company?: string;
  role?: string;
  job_url?: string | null;
  jd_snapshot?: Record<string, unknown> | null;
  status?: ApplicationStatus;
  status_change_note?: string | null;
  next_action?: string | null;
  follow_up_at?: string | null;
  notes?: string | null;
}
