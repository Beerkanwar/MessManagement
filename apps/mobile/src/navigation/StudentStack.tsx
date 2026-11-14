// Student Stack Navigator per Build Item 7, App Flow §3
import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { StudentStackParamList } from './navigationTypes';
import { StudentHomeScreen } from '../features/student/StudentHomeScreen';
import { StudentDestinationPlaceholderScreen } from '../features/student/StudentDestinationPlaceholderScreen';
import { DiagnosticsScreen } from '../features/diagnostics/DiagnosticsScreen';

const Stack = createNativeStackNavigator<StudentStackParamList>();

export const StudentStack: React.FC = () => {
  return (
    <Stack.Navigator
      initialRouteName="StudentHome"
      screenOptions={{
        headerShown: false,
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="StudentHome" component={StudentHomeScreen as any} />
      <Stack.Screen name="Diagnostics" component={DiagnosticsScreen as any} />
      <Stack.Screen name="my-qr" component={StudentDestinationPlaceholderScreen as any} />
      <Stack.Screen name="attendance" component={StudentDestinationPlaceholderScreen as any} />
      <Stack.Screen name="billing" component={StudentDestinationPlaceholderScreen as any} />
      <Stack.Screen name="wallet" component={StudentDestinationPlaceholderScreen as any} />
      <Stack.Screen name="extras" component={StudentDestinationPlaceholderScreen as any} />
      <Stack.Screen name="pause" component={StudentDestinationPlaceholderScreen as any} />
      <Stack.Screen name="feedback" component={StudentDestinationPlaceholderScreen as any} />
    </Stack.Navigator>
  );
};
