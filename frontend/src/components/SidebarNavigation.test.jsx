import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import SidebarNavigation, { activeNavigationPath, navigation, STORAGE_KEY } from './SidebarNavigation';

let mockPath = '/animals/repeat-breeders';
jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
  useLocation: () => ({ pathname: mockPath }),
}), { virtual: true });

let container, root;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

test('auto-expands the active alias parent and persists toggles', () => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ Breeding: false, Animals: false }));
  act(() => root.render(<SidebarNavigation role="viewer" />));
  const breeding = container.querySelector('[aria-controls="nav-group-breeding"]');
  expect(breeding.getAttribute('aria-expanded')).toBe('true');
  expect(container.querySelectorAll('[aria-current="page"]')).toHaveLength(1);
  expect(container.querySelector('[aria-current="page"]').textContent).toContain('Repeat Breeders');
  act(() => breeding.click());
  expect(JSON.parse(localStorage.getItem(STORAGE_KEY)).Breeding).toBe(false);
  act(() => root.unmount());
  root = createRoot(container);
  mockPath = '/';
  act(() => root.render(<SidebarNavigation role="viewer" />));
  expect(container.querySelector('[aria-controls="nav-group-breeding"]').getAttribute('aria-expanded')).toBe('false');
});

test('uses the most specific route and hides restricted links', () => {
  expect(activeNavigationPath('/daily-logs/new')).toBe('/daily-logs/new');
  expect(activeNavigationPath('/reports/mortality')).toBe('/mortality');
  expect(activeNavigationPath('/animals/12')).toBe('/animals');
  mockPath = '/reproduction/status';
  localStorage.setItem(STORAGE_KEY, 'invalid JSON');
  act(() => root.render(<SidebarNavigation role="viewer" />));
  expect(container.querySelector('a[href="/settings"]')).toBeNull();
  expect(container.querySelector('a[href="/daily-logs/new"]')).toBeNull();
  expect(container.querySelector('[aria-current="page"]').textContent).toContain('Status Board');
  act(() => root.render(<SidebarNavigation role="admin" />));
  expect(container.querySelector('a[href="/settings"]')).not.toBeNull();
  expect(container.querySelector('a[href="/daily-logs/new"]')).not.toBeNull();
});

test('keeps every previous working navigation destination directly or as an alias', () => {
  const paths = navigation.flatMap((group) => group.children || [group]).flatMap((link) => [link.path, ...link.aliases]);
  ['/', '/locations', '/animals', '/reproduction', '/farm-health', '/daily-logs', '/opening-balances', '/reports', '/reports/mortality', '/reconciliation', '/settings', '/admin/users'].forEach((path) => expect(paths).toContain(path));
});
