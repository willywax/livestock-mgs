import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ReproductiveEventDialog from './ReproductiveEventDialog';
import { createReproductiveEvent } from '../lib/api';

jest.mock('../lib/api', () => ({ createReproductiveEvent: jest.fn(), getAnimals: jest.fn() }));
jest.mock('./ReproductionDialogs', () => ({ getTerms: () => ({ event: 'Calving', male: 'Bull' }), toISODate: () => '2026-11-10' }));

test.each([
  ['calving', { calving_outcome: 'live', offspring_count: 1 }],
  ['service', { service_type: 'natural' }],
  ['pd_test', { pd_result: 'pregnant', months_pregnant: null, vet: null }],
])('reuses the event form with preselected %s and the correct animal', async (type, fields) => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  createReproductiveEvent.mockResolvedValue({ data: {} });
  const onSaved = jest.fn();
  const onClose = jest.fn();
  const container = document.createElement('div'); document.body.appendChild(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<ReproductiveEventDialog animal={{ id: 42, species: 'cattle' }} initialType={type} onSaved={onSaved} onClose={onClose} />));
    await act(async () => document.querySelector('[role="dialog"] form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
    expect(createReproductiveEvent).toHaveBeenLastCalledWith(42, { event_type: type, event_date: '2026-11-10', notes: null, ...fields });
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  } finally { act(() => root.unmount()); container.remove(); }
});
