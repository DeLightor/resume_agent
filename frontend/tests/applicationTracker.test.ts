import { test } from 'node:test';
import assert from 'node:assert/strict';
import { applicationPayload, statusMeta } from '../src/lib/applicationTracker.ts';

test('status has visible Chinese label and non-color semantic', () => {
  assert.deepEqual(statusMeta('interview'), { label: '面试', tone: 'brand' });
});

test('creation payload keeps edited JD but never sends a resume snapshot or version', () => {
  const payload = applicationPayload({
    resume_node_id: 'backend', company: 'OpenAI', role: 'Engineer',
    jd_snapshot: { company: 'Edited OpenAI', job_title: 'Engineer' },
    resume_snapshot: { personal_info: { name: '不应发送' } }, resume_version: 42,
  });
  assert.deepEqual(payload, {
    resume_node_id: 'backend', company: 'OpenAI', role: 'Engineer',
    jd_snapshot: { company: 'Edited OpenAI', job_title: 'Engineer' },
  });
});
