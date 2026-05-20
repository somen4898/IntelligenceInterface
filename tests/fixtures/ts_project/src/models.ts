/** A user in the system. */
export interface User {
  id: number;
  name: string;
  email: string;
}

/** A product listing. */
export interface Product {
  id: number;
  title: string;
  price: number;
}

/** Base class for all services. */
export class BaseService {
  protected db: any;

  constructor(db: any) {
    this.db = db;
  }

  /** Log a message. */
  log(message: string): void {
    console.log(message);
  }
}

/** Maximum number of items per page. */
export const MAX_PAGE_SIZE = 100;

/** Format a user for display. */
export function formatUser(user: User): string {
  return `${user.name} <${user.email}>`;
}

export type UserRole = "admin" | "user" | "guest";
