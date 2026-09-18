import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { expect, it } from 'vitest';
import { SkillSynonymPage } from './SkillSynonymPage';
it('opens a governed skill entry editor and keeps ambiguous aliases visible', () => {
  render(
    <MemoryRouter>
      <SkillSynonymPage />
    </MemoryRouter>,
  );
  expect(screen.getByRole('heading', { name: '技能同义词库' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /新增词条/ }));
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  expect(screen.getByText('歧义别名')).toBeInTheDocument();
}, 15000);
