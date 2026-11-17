import { computed, ref } from 'vue';
import { z } from 'zod';
import { hrRequest, hrWrite } from '../../entities/hr';
export const dimensions = ['SKILL', 'EXPERIENCE', 'PROJECT', 'EDUCATION', 'BONUS'] as const;
export const scoringSchema = z.object({
  version: z.string(),
  weights: z.record(z.enum(dimensions), z.number()),
  requirements: z.array(
    z.object({
      id: z.string(),
      dimension: z.enum(dimensions),
      weight: z.number(),
      critical: z.boolean(),
      applicable: z.boolean(),
    }),
  ),
  highThreshold: z.number(),
  middleThreshold: z.number(),
  lowThreshold: z.number(),
  minimumCoverage: z.number(),
  strongCoverage: z.number(),
});
export const ruleSchema = z.object({
  id: z.string(),
  type: z.string(),
  label: z.string(),
  expected: z
    .string()
    .nullable()
    .transform((value) => value ?? ''),
  unit: z
    .string()
    .nullable()
    .transform((value) => value ?? ''),
  threshold: z.number().nullable(),
  tolerance: z.number().nullable(),
  overridable: z.boolean(),
  values: z.array(z.string()),
  matchMode: z
    .string()
    .nullable()
    .transform((value) => value ?? ''),
});
export const calculationSchema = z.object({
  type: z.enum([
    'EXPERIENCE_MONTHS',
    'EDUCATION_RANK',
    'PROJECT_SCALE',
    'PROJECT_ROLE',
    'TEAM_SIZE',
    'BONUS_DECLARATION',
  ]),
  minimum: z.number().nullable(),
  maximum: z.number().nullable(),
  expected: z.number().nullable(),
  metric: z.string().nullable(),
  unit: z.string().nullable(),
});
export const criterionSchema = z.object({
  calculation: calculationSchema.nullish(),
  id: z.string(),
  label: z.string(),
  dimension: z.enum(dimensions),
  criterion: z.string(),
  strongAnchor: z.string(),
  matchAnchor: z.string(),
  partialAnchor: z.string(),
  notMetAnchor: z.string(),
  critical: z.boolean(),
});
export const visibleMarkKeys = [
  'MANUAL_REVIEW',
  'BORDERLINE',
  'QUALITY_WARNING',
  'DUPLICATE',
  'SPECIAL_BACKGROUND',
] as const;
export const draftSchema = z.object({
  visibleMarks: z.array(z.enum(visibleMarkKeys)).default([...visibleMarkKeys]),
  positionId: z.string(),
  name: z.string(),
  family: z.string(),
  departmentId: z.string(),
  level: z.string(),
  jdText: z
    .string()
    .nullable()
    .transform((value) => value ?? ''),
  lastStep: z.string(),
  scoring: scoringSchema.nullable(),
  draftScoring: scoringSchema.nullable().optional(),
  hardConditions: z.array(ruleSchema),
  criteria: z.array(criterionSchema),
  version: z.number(),
});
export type PositionDraft = z.infer<typeof draftSchema>;
export const loadPositionDraft = (id: string, signal?: AbortSignal) =>
  hrRequest(`/positions/${encodeURIComponent(id)}/draft`, draftSchema, { signal });
export const savePositionDraft = (draft: z.input<typeof draftSchema>) =>
  hrRequest(`/positions/${encodeURIComponent(draft.positionId)}/draft`, draftSchema, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify(draft),
  });
export function useHrPositionDraft() {
  const draft = ref<PositionDraft>();
  const busy = ref(false);
  const error = ref('');
  const dirty = ref(false);
  const conflict = computed(() => error.value.includes('冲突') || error.value.includes('其他人'));
  async function load(id: string, signal?: AbortSignal) {
    busy.value = true;
    error.value = '';
    try {
      draft.value = await loadPositionDraft(id, signal);
      dirty.value = false;
    } catch (e) {
      if (!(e instanceof DOMException && e.name === 'AbortError'))
        error.value = e instanceof Error ? e.message : '草稿读取失败';
    } finally {
      busy.value = false;
    }
  }
  async function create(input: {
    name: string;
    family: string;
    departmentId: string;
    level: string;
  }) {
    if (busy.value) return;
    busy.value = true;
    error.value = '';
    try {
      const position = await hrWrite('/positions', z.object({ id: z.string() }), input);
      draft.value = await loadPositionDraft(position.id);
      return position.id;
    } catch (e) {
      error.value = e instanceof Error ? e.message : '岗位创建失败';
    } finally {
      busy.value = false;
    }
  }
  async function save(step: string) {
    if (!draft.value || busy.value) return false;
    busy.value = true;
    error.value = '';
    try {
      draft.value = await savePositionDraft({ ...draft.value, lastStep: step });
      dirty.value = false;
      return true;
    } catch (e) {
      error.value = e instanceof Error ? e.message : '草稿保存失败';
      return false;
    } finally {
      busy.value = false;
    }
  }
  return { draft, busy, error, dirty, conflict, load, create, save };
}
