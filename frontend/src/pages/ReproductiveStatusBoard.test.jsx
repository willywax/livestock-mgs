import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ReproductiveStatusBoard, { BUCKETS, BucketCard } from './ReproductiveStatusBoard';
import { getLocations, getReproductiveStatusBoard } from '../lib/api';

let mockCanWrite = false;
jest.mock('../lib/api', () => ({ getLocations: jest.fn(), getReproductiveStatusBoard: jest.fn() }));
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ isDataEntry: mockCanWrite }) }));
jest.mock('react-router-dom', () => ({ Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a> }), { virtual: true });
jest.mock('../components/ReproductiveEventDialog', () => ({ animal, initialType, onSaved }) => <button onClick={onSaved}>Save {initialType} for {animal.tag_number}</button>);

const cow = { id: 12, tag_number: 'C-12', category: 'Koo', farm: 'Farm A', reproductive_status: 'pregnant', months_pregnant: 8, services_without_conception: 5, last_event_date: '2026-11-01' };
const response = () => ({ summary: { total_breeding_females: 1, status_known_pct: 100 }, ...Object.fromEntries(BUCKETS.map(({ key, title }) => [key, { label: title, count: key === 'pregnant' ? 1 : 0, animals: key === 'pregnant' ? [cow] : [] }])) });
let container, root;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  mockCanWrite = false;
  jest.clearAllMocks();
  getLocations.mockResolvedValue({ data: [{ id: 1, name: 'Farm A' }] });
  getReproductiveStatusBoard.mockResolvedValue({ data: response() });
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

test('loads filters, hides viewer write actions, and opens a prefilled modal for writers', async () => {
  await act(async () => root.render(<ReproductiveStatusBoard />));
  expect(container.textContent).toContain('1 breeding females');
  expect(container.textContent).not.toContain('Record calving');
  expect(container.querySelector('a[href="/animals/12"]')).not.toBeNull();
  mockCanWrite = true;
  await act(async () => root.render(<ReproductiveStatusBoard />));
  const calving = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Record calving');
  await act(async () => calving.click());
  expect(container.textContent).toContain('Save calving for C-12');
  const save = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Save calving for C-12');
  await act(async () => save.click());
  expect(getReproductiveStatusBoard).toHaveBeenCalledTimes(2);
  const farm = container.querySelector('select[aria-label="Farm"]');
  await act(async () => { farm.value = '1'; farm.dispatchEvent(new Event('change', { bubbles: true })); });
  const goats = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Goats');
  await act(async () => goats.click());
  expect(getReproductiveStatusBoard).toHaveBeenLastCalledWith({ farm_id: 1, species: 'goat' });
});

test('ignores late responses from an earlier filter', async () => {
  let finishOld;
  getReproductiveStatusBoard.mockImplementationOnce(() => new Promise((resolve) => { finishOld = resolve; }));
  await act(async () => root.render(<ReproductiveStatusBoard />));
  const sheep = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Sheep');
  const latest = response(); latest.summary.total_breeding_females = 7;
  getReproductiveStatusBoard.mockResolvedValue({ data: latest });
  await act(async () => sheep.click());
  await act(async () => finishOld({ data: response() }));
  expect(container.textContent).toContain('7 breeding females');
});

test('empty cards collapse, repeat rows show severity, and attention uses detail links', async () => {
  const config = BUCKETS.find((bucket) => bucket.key === 'due_this_month');
  await act(async () => root.render(<BucketCard config={config} bucket={{ count: 0, animals: [] }} />));
  expect(container.querySelector('[aria-expanded]').getAttribute('aria-expanded')).toBe('false');
  await act(async () => container.querySelector('button').click());
  expect(container.querySelector('[id="bucket-due_this_month"]').hidden).toBe(false);
  expect(container.textContent).toContain('No animals due in the next 30 days.');
  await act(async () => root.render(<BucketCard config={BUCKETS.find((b) => b.key === 'repeat_breeders')} bucket={{ count: 1, animals: [cow] }} />));
  expect(container.querySelector('tbody tr').className).toContain('bg-red-50');
  expect(container.textContent).toContain('Failed services');
  await act(async () => root.render(<BucketCard config={BUCKETS.find((b) => b.key === 'needs_attention')} bucket={{ count: 1, animals: [cow] }} canWrite />));
  expect(container.textContent).toContain('View animal');
  expect(container.textContent).not.toContain('Record calving');
});

test('shows an error instead of presenting failed loads as empty herd counts', async () => {
  getReproductiveStatusBoard.mockRejectedValue(new Error('Unavailable'));
  await act(async () => root.render(<ReproductiveStatusBoard />));
  expect(container.querySelector('[role="alert"]').textContent).toContain('Unable to load');
  expect(container.textContent).not.toContain('0 breeding females');
});
