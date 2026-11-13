import React, { useState } from 'react';
import { TextField, TextFieldProps } from './TextField';
import { Icons } from './Icons';

export interface PasswordFieldProps extends Omit<TextFieldProps, 'type' | 'endIcon'> {}

export const PasswordField = React.forwardRef<HTMLInputElement, PasswordFieldProps>((props, ref) => {
  const [showPassword, setShowPassword] = useState(false);

  return (
    <TextField
      ref={ref}
      type={showPassword ? 'text' : 'password'}
      endIcon={
        <button
          type="button"
          onClick={() => setShowPassword(!showPassword)}
          className="text-text-muted hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded p-1"
          aria-label={showPassword ? 'Hide password' : 'Show password'}
        >
          {showPassword ? <Icons.EyeOff className="w-4 h-4" /> : <Icons.Eye className="w-4 h-4" />}
        </button>
      }
      {...props}
    />
  );
});
PasswordField.displayName = 'PasswordField';

