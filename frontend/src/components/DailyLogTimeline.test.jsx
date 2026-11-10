import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import DailyLogTimeline from './DailyLogTimeline';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { getAnimalDailyLogTimeline } from '../lib/api';

jest.mock('../lib/api', () => ({ getAnimalDailyLogTimeline: jest.fn() }));
jest.mock('react-router-dom', () => ({ Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a> }), { virtual: true });
const event = (id) => ({ event_id: id, event_type: 'pd_test', event_type_label: 'PD test', event_date: '2026-11-01',
  farm_name: 'Farm A', daily_log_id: 2, notes: 'a'.repeat(70), quantity: 1, result: 'pregnant', recorded_by_name: 'Admin' });
let container, root;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  getAnimalDailyLogTimeline.mockReset();
  getAnimalDailyLogTimeline.mockResolvedValue({ data: { items: [], total: 0, page: 1, page_size: 20 } });
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

test('the tab loads only on activation', async () => {
  await act(async () => root.render(<Tabs defaultValue="activity"><TabsList><TabsTrigger value="activity">Activity</TabsTrigger><TabsTrigger value="logs">Daily Log Timeline</TabsTrigger></TabsList><TabsContent value="activity">Activity feed</TabsContent><TabsContent value="logs"><DailyLogTimeline animalId={1} /></TabsContent></Tabs>));
  expect(getAnimalDailyLogTimeline).not.toHaveBeenCalled();
  await act(async () => container.querySelector('[role="tab"][data-state="inactive"]').dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 })));
  expect(getAnimalDailyLogTimeline).toHaveBeenCalledWith(1, { page: 1, page_size: 20 });
  expect(container.textContent).toContain('No events recorded for this animal yet.');
});

test('load more appends rows, filters restart paging, and notes are truncated', async () => {
  getAnimalDailyLogTimeline.mockResolvedValueOnce({ data: { items: [event(2)], total: 2 } })
    .mockResolvedValueOnce({ data: { items: [event(1)], total: 2 } });
  await act(async () => root.render(<DailyLogTimeline animalId={1} />));
  expect(container.querySelectorAll('li')).toHaveLength(1);
  expect(container.querySelector('[title]').textContent).toBe('a'.repeat(60) + '…');
  expect(container.querySelector('a').getAttribute('href')).toBe('/daily-logs/2');
  await act(async () => container.querySelector('button').click());
  expect(getAnimalDailyLogTimeline).toHaveBeenLastCalledWith(1, { page: 2, page_size: 20 });
  expect(container.querySelectorAll('li')).toHaveLength(2);
  const select = container.querySelector('select');
  await act(async () => { select.value = 'death'; select.dispatchEvent(new Event('change', { bubbles: true })); });
  expect(getAnimalDailyLogTimeline).toHaveBeenLastCalledWith(1, { page: 1, page_size: 20, event_type: 'death' });
  expect(container.querySelectorAll('li')).toHaveLength(0);
});

test('ignores stale filter responses and exposes failed loads for retry', async () => {
  let resolveOld;
  getAnimalDailyLogTimeline.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
  await act(async () => root.render(<DailyLogTimeline animalId={1} />));
  const select = container.querySelector('select');
  await act(async () => { select.value = 'service'; select.dispatchEvent(new Event('change', { bubbles: true })); });
  await act(async () => resolveOld({ data: { items: [event(99)], total: 1 } }));
  expect(container.querySelectorAll('li')).toHaveLength(0);
  getAnimalDailyLogTimeline.mockRejectedValueOnce(new Error('offline'));
  await act(async () => { select.value = 'birth'; select.dispatchEvent(new Event('change', { bubbles: true })); });
  expect(container.querySelector('[role="alert"]')).not.toBeNull();
  await act(async () => container.querySelector('button').click());
  expect(container.querySelector('[role="alert"]')).toBeNull();
});
