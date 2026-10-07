// Mirrors backend/auth.py so people get instant feedback; the server still
// has the final say.

export const NAME_MIN = 2;
export const NAME_MAX = 60;
export const QUESTION_MAX = 500; // security/input_validation.py MAX_QUESTION_LENGTH

export function validateName(raw: string): string | null {
  const name = raw.replace(/\s+/g, " ").trim();
  if (name.length < NAME_MIN) return "Enter your name.";
  if (name.length > NAME_MAX) return `Keep your name under ${NAME_MAX} characters.`;
  if (!/^[\p{L}][\p{L} .'-]*$/u.test(name) || (name.match(/\p{L}/gu) ?? []).length < 2) {
    return "Use letters, spaces, . ' and - only.";
  }
  return null;
}

export const normalizePhone = (raw: string): string => raw.replace(/[\s\-().]/g, "");

export function validatePhone(raw: string): string | null {
  if (!raw.trim()) return "Enter your phone number.";
  if (!/^\+?\d{10,15}$/.test(normalizePhone(raw))) {
    return "Enter 10 to 15 digits. A + country code is fine.";
  }
  return null;
}
