import { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';

interface StreamingAssistantContentProps {
  content: string;
  mode: 'typing' | 'complete' | 'frozen';
}

const typingIntervalMs = 24;

function splitGraphemes(content: string): string[] {
  return Array.from(new Intl.Segmenter('zh-CN', { granularity: 'grapheme' }).segment(content)).map(
    ({ segment }) => segment,
  );
}

function getReducedMotionPreference(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
}

export function StreamingAssistantContent({ content, mode }: StreamingAssistantContentProps) {
  const graphemes = useMemo(() => splitGraphemes(content), [content]);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(getReducedMotionPreference);
  const [visibleCount, setVisibleCount] = useState(() =>
    getReducedMotionPreference() ? graphemes.length : 0,
  );

  useEffect(() => {
    const mediaQuery = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!mediaQuery) return;
    const updatePreference = (event: MediaQueryListEvent) => setPrefersReducedMotion(event.matches);
    mediaQuery.addEventListener('change', updatePreference);
    return () => mediaQuery.removeEventListener('change', updatePreference);
  }, []);

  useEffect(() => {
    if (prefersReducedMotion || mode === 'frozen' || visibleCount >= graphemes.length) return;
    const timer = window.setInterval(() => {
      setVisibleCount((current) => Math.min(current + 1, graphemes.length));
    }, typingIntervalMs);
    return () => window.clearInterval(timer);
  }, [graphemes.length, mode, prefersReducedMotion, visibleCount]);

  const visibleContent = prefersReducedMotion ? content : graphemes.slice(0, visibleCount).join('');

  return (
    <div aria-label="助手回复">
      <ReactMarkdown
        skipHtml
        components={{
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {visibleContent}
      </ReactMarkdown>
    </div>
  );
}
