import type { ApplicationStatus, CreateApplicationRequest } from '@/types/application';

export const APPLICATION_STATUSES: ApplicationStatus[] = [
  'draft', 'applied', 'hr_screen', 'interview', 'offer', 'rejected', 'withdrawn',
];

const STATUS_META: Record<ApplicationStatus, { label: string; tone: 'muted' | 'brand' | 'warning' | 'success' | 'danger' }> = {
  draft: { label: '草稿', tone: 'muted' },
  applied: { label: '已投递', tone: 'brand' },
  hr_screen: { label: 'HR 沟通', tone: 'warning' },
  interview: { label: '面试', tone: 'brand' },
  offer: { label: 'Offer', tone: 'success' },
  rejected: { label: '已拒绝', tone: 'danger' },
  withdrawn: { label: '已撤回', tone: 'muted' },
};

export function statusMeta(status: ApplicationStatus) { return STATUS_META[status]; }

/** Remove presentation-only fields before a create request crosses the trust boundary. */
export function applicationPayload(input: Record<string, unknown>): CreateApplicationRequest {
  const payload: CreateApplicationRequest = {
    resume_node_id: String(input.resume_node_id ?? ''),
    company: String(input.company ?? ''),
    role: String(input.role ?? ''),
  };
  for (const key of ['job_url', 'jd_snapshot', 'status', 'next_action', 'follow_up_at', 'notes'] as const) {
    if (input[key] !== undefined) Object.assign(payload, { [key]: input[key] });
  }
  return payload;
}

export function localDateTimeToUtc(value: string): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? null : parsed.toISOString().replace('.000Z', 'Z');
}

export function utcToLocalDateTime(value: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return '';
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.valueOf() - offset).toISOString().slice(0, 16);
}
