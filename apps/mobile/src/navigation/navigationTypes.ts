// Navigation Type Definitions per SDD §7, Build Item 7

export type AuthStackParamList = {
  SignIn: undefined;
  ForgotPassword: undefined;
  ChangePassword: undefined;
};

export type StudentStackParamList = {
  StudentHome: undefined;
  Diagnostics: undefined;
  'my-qr': { title?: string; description?: string } | undefined;
  attendance: { title?: string; description?: string } | undefined;
  billing: { title?: string; description?: string } | undefined;
  wallet: { title?: string; description?: string } | undefined;
  extras: { title?: string; description?: string } | undefined;
  pause: { title?: string; description?: string } | undefined;
  feedback: { title?: string; description?: string } | undefined;
};

export type ManagerStackParamList = {
  ManagerHome: undefined;
  Diagnostics: undefined;
  'record-meal': { title?: string; description?: string } | undefined;
  'record-extras': { title?: string; description?: string } | undefined;
  'live-roster': { title?: string; description?: string } | undefined;
  'sync-status': { title?: string; description?: string } | undefined;
  announcements: { title?: string; description?: string } | undefined;
  'daily-summary': { title?: string; description?: string } | undefined;
};
