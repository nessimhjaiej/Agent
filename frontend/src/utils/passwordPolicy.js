export function getPasswordChecks(password = '') {
  return {
    minLength: password.length >= 8,
    hasUpper: /[A-Z]/.test(password),
    hasLower: /[a-z]/.test(password),
    hasDigit: /\d/.test(password),
    hasSpecial: /[^A-Za-z0-9]/.test(password),
  };
}

export function isPasswordStrong(password = '') {
  return Object.values(getPasswordChecks(password)).every(Boolean);
}

export const PASSWORD_POLICY_MESSAGE =
  'Password must be at least 8 characters and include at least 1 uppercase letter, 1 lowercase letter, 1 number, and 1 special character.';
