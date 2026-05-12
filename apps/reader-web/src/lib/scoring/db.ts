import { Pool } from "pg";
import { getConfig } from "@/lib/config";

let pool: Pool | undefined;

export function getPool() {
  if (!pool) {
    pool = new Pool({
      connectionString: getConfig().SCORING_DATABASE_URL,
      max: 5,
    });
  }
  return pool;
}
