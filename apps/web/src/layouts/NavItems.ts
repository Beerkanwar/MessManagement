export interface NavLinkItem {
  label: string;
  path: string;
  iconName: string;
}

export interface NavGroup {
  groupTitle?: string;
  items: NavLinkItem[];
}

export const CLERK_NAV: NavGroup[] = [
  {
    items: [
      { label: 'Dashboard', path: '/clerk/dashboard', iconName: 'dashboard' },
      { label: 'Student Verification', path: '/clerk/verifications', iconName: 'checkCircle' },
      { label: 'Menu', path: '/clerk/menu', iconName: 'calendar' },
      { label: 'Extra Items', path: '/clerk/extras', iconName: 'plus' },
      { label: 'Attendance', path: '/clerk/attendance', iconName: 'clock' },
      { label: 'Bills', path: '/clerk/bills', iconName: 'rupee' },
      { label: 'Feedback', path: '/clerk/feedback', iconName: 'chat' },
      { label: 'Reports', path: '/clerk/reports', iconName: 'chart' },
    ],
  },
];

export const ADMIN_NAV: NavGroup[] = [
  {
    items: [
      { label: 'Dashboard', path: '/admin/dashboard', iconName: 'dashboard' },
    ],
  },
  {
    groupTitle: 'People and places',
    items: [
      { label: 'Hostels', path: '/admin/hostels', iconName: 'home' },
      { label: 'Messes', path: '/admin/messes', iconName: 'coffee' },
      { label: 'Students', path: '/admin/students', iconName: 'users' },
      { label: 'Hostel Clerks', path: '/admin/clerks', iconName: 'userCheck' },
      { label: 'Mess Managers', path: '/admin/managers', iconName: 'userCog' },
    ],
  },
  {
    groupTitle: 'Money',
    items: [
      { label: 'Meal Configuration', path: '/admin/meal-config', iconName: 'utensils' },
      { label: 'Pricing', path: '/admin/pricing', iconName: 'tag' },
      { label: 'Billing', path: '/admin/billing', iconName: 'receipt' },
    ],
  },
  {
    groupTitle: 'Operations',
    items: [
      { label: 'Devices', path: '/admin/devices', iconName: 'smartphone' },
      { label: 'Synchronization', path: '/admin/sync', iconName: 'refresh' },
      { label: 'Reports', path: '/admin/reports', iconName: 'chart' },
    ],
  },
  {
    groupTitle: 'System',
    items: [
      { label: 'Audit Logs', path: '/admin/audit', iconName: 'fileText' },
      { label: 'System Configuration', path: '/admin/settings', iconName: 'sliders' },
    ],
  },
];

