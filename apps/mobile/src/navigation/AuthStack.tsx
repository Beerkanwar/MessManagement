// Auth Stack Navigator per Build Item 7
import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { AuthStackParamList } from './navigationTypes';
import { SignInScreen } from '../features/auth/SignInScreen';
import { ForgotPasswordScreen } from '../features/auth/ForgotPasswordScreen';
import { ChangePasswordScreen } from '../features/auth/ChangePasswordScreen';

const Stack = createNativeStackNavigator<AuthStackParamList>();

export const AuthStack: React.FC = () => {
  return (
    <Stack.Navigator
      initialRouteName="SignIn"
      screenOptions={{
        headerShown: false,
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="SignIn" component={SignInScreen as any} />
      <Stack.Screen name="ForgotPassword" component={ForgotPasswordScreen as any} />
      <Stack.Screen name="ChangePassword" component={ChangePasswordScreen as any} />
    </Stack.Navigator>
  );
};
