// Manager Stack Navigator per Build Item 7, App Flow §4
import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { ManagerStackParamList } from './navigationTypes';
import { ManagerHomeScreen } from '../features/manager/ManagerHomeScreen';
import { ManagerDestinationPlaceholderScreen } from '../features/manager/ManagerDestinationPlaceholderScreen';
import { DiagnosticsScreen } from '../features/diagnostics/DiagnosticsScreen';

const Stack = createNativeStackNavigator<ManagerStackParamList>();

export const ManagerStack: React.FC = () => {
  return (
    <Stack.Navigator
      initialRouteName="ManagerHome"
      screenOptions={{
        headerShown: false,
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="ManagerHome" component={ManagerHomeScreen as any} />
      <Stack.Screen name="Diagnostics" component={DiagnosticsScreen as any} />
      <Stack.Screen name="record-meal" component={ManagerDestinationPlaceholderScreen as any} />
      <Stack.Screen name="record-extras" component={ManagerDestinationPlaceholderScreen as any} />
      <Stack.Screen name="live-roster" component={ManagerDestinationPlaceholderScreen as any} />
      <Stack.Screen name="sync-status" component={ManagerDestinationPlaceholderScreen as any} />
      <Stack.Screen name="announcements" component={ManagerDestinationPlaceholderScreen as any} />
      <Stack.Screen name="daily-summary" component={ManagerDestinationPlaceholderScreen as any} />
    </Stack.Navigator>
  );
};
