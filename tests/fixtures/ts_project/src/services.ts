import { User, Product, BaseService } from "./models";

/** Manages user operations. */
export class UserService extends BaseService {
  /** Create a new user. */
  async createUser(name: string, email: string): Promise<User> {
    this.log(`Creating user: ${name}`);
    return { id: 1, name, email };
  }

  /** Delete a user by ID. */
  async deleteUser(id: number): Promise<boolean> {
    return true;
  }
}

/** Fetch a user by ID. */
export const getUser = async (id: number): Promise<User | null> => {
  return null;
};

/** Create a product. */
export const createProduct = (title: string, price: number): Product => {
  return { id: 1, title, price };
};
