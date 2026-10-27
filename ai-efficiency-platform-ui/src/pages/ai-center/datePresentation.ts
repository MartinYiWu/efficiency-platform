const minuteFormat = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

export const formatAiDate = (value: string | null | undefined) =>
  value ? minuteFormat.format(new Date(value)).replaceAll('/', '-') : '—';
