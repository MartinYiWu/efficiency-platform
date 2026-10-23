import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { KnowledgeUploadDrawer } from './KnowledgeUploadDrawer';

it('offers extractive narrative only for product and technical uploads', () => {
  render(
    <KnowledgeUploadDrawer
      open
      baseId="kb"
      knowledgeType="PRODUCT_DOCUMENTATION"
      directories={[]}
      onClose={() => {}}
      onSubmitted={() => {}}
    />,
  );
  expect(screen.getByRole('combobox', { name: '证据处理' })).toBeEnabled();
  expect(screen.getByText(/仅选择原文句段/)).toBeInTheDocument();
});

it('locks policy uploads to full text', () => {
  render(
    <KnowledgeUploadDrawer
      open
      baseId="kb"
      knowledgeType="COMPANY_POLICY"
      directories={[]}
      onClose={() => {}}
      onSubmitted={() => {}}
    />,
  );
  expect(screen.getByRole('combobox', { name: '证据处理' })).toBeDisabled();
});
