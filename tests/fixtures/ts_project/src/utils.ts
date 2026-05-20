import { User } from "./models";

/** Validate an email address. */
export function validateEmail(email: string): boolean {
  return email.includes("@");
}

/** Get user initials. */
export function getUserInitials(user: User): string {
  return user.name.split(" ").map(n => n[0]).join("");
}

export default validateEmail;
