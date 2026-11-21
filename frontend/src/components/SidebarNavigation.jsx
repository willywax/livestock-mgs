import React, { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { House, Tag, CalendarBlank, Horse, Scales, ChartBar, Gear, MapPin, FirstAidKit, CaretRight } from '@phosphor-icons/react';
import { cn } from '../lib/utils';

const all = ['admin', 'data_entry', 'viewer'];
const writers = ['admin', 'data_entry'];
const item = (label, path, roles = all, aliases = []) => ({ label, path, roles, aliases });
export const navigation = [
  { ...item('Dashboard', '/'), icon: House },
  { label: 'Animals', icon: Tag, children: [item('Animal Register', '/animals'), item('Transition Queue', '/animals/transitions', writers), item('Tag Reconciliation', '/reconciliation')] },
  { label: 'Daily Logs', icon: CalendarBlank, children: [item('Log List', '/daily-logs'), item('Add Log', '/daily-logs/new', writers)] },
  { label: 'Breeding', icon: Horse, children: [item('Status Board', '/reproduction/status'), item('Cycles & Records', '/reproduction'), item('Repeat Breeders', '/repeat-breeders', all, ['/animals/repeat-breeders'])] },
  { label: 'Stock', icon: Scales, children: [item('Overview', '/stock'), item('Opening Balances', '/opening-balances', ['admin'])] },
  { label: 'Reports', icon: ChartBar, children: [item('Sales', '/reports/sales'), item('Mortality', '/mortality', all, ['/reports/mortality']), item('Daily / Range Reports', '/reports')] },
  { label: 'Admin', icon: Gear, children: [item('Settings', '/settings', ['admin']), item('Users', '/users', ['admin'], ['/admin/users']), item('Customers', '/customers')] },
  { ...item('Locations', '/locations'), icon: MapPin },
  { ...item('Farm Health', '/farm-health'), icon: FirstAidKit },
];
export const STORAGE_KEY = 'shamba.sidebar.groups.v1';

export function activeNavigationPath(pathname) {
  const links = navigation.flatMap((group) => group.children || [group]);
  return links.flatMap((link) => [link.path, ...link.aliases].map((path) => ({ path, target: link.path })))
    .filter(({ path }) => pathname === path || (path !== '/' && pathname.startsWith(path + '/')))
    .sort((a, b) => b.path.length - a.path.length)[0]?.target;
}

export function readGroupState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {};
  } catch { return {}; }
}

export default function SidebarNavigation({ role, onNavigate }) {
  const { pathname } = useLocation();
  const activePath = activeNavigationPath(pathname);
  const activeGroup = navigation.find((group) => group.children?.some((child) => child.path === activePath))?.label;
  const [expanded, setExpanded] = useState(() => ({ ...readGroupState(), ...(activeGroup ? { [activeGroup]: true } : {}) }));
  useEffect(() => {
    if (activeGroup) setExpanded((previous) => ({ ...previous, [activeGroup]: true }));
  }, [activeGroup, pathname]);
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(expanded)); } catch { /* Storage may be disabled. */ }
  }, [expanded]);

  const renderLink = (link, nested = false, Icon) => (
    <Link key={link.path} to={link.path} onClick={onNavigate} aria-current={activePath === link.path ? 'page' : undefined}
      className={cn('flex items-center gap-3 rounded-r-md border-l-2 px-3 py-2 transition-colors',
        nested ? 'ml-4 text-sm' : 'font-medium',
        activePath === link.path ? 'border-primary bg-primary/10 text-primary' : 'border-transparent text-muted-foreground hover:bg-muted hover:text-foreground')}>
      {Icon && <Icon className="h-5 w-5" />} {link.label}
    </Link>
  );
  return <nav aria-label="Main navigation" className="p-4 space-y-2">
    {navigation.map((group) => {
      if (!group.children) return group.roles.includes(role) ? renderLink(group, false, group.icon) : null;
      const children = group.children.filter((child) => child.roles.includes(role));
      if (!children.length) return null;
      const Icon = group.icon;
      const open = !!expanded[group.label];
      const id = `nav-group-${group.label.toLowerCase().replaceAll(' ', '-')}`;
      return <div key={group.label}>
        <button type="button" aria-expanded={open} aria-controls={id}
          onClick={() => setExpanded((previous) => ({ ...previous, [group.label]: !previous[group.label] }))}
          className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-base font-semibold uppercase tracking-wide text-muted-foreground hover:bg-muted">
          <Icon className="h-5 w-5 shrink-0" /><span className="flex-1">{group.label}</span>
          <CaretRight className={cn('h-4 w-4 transition-transform', open && 'rotate-90')} />
        </button>
        <div id={id} hidden={!open}>{children.map((child) => renderLink(child, true))}</div>
      </div>;
    })}
  </nav>;
}
