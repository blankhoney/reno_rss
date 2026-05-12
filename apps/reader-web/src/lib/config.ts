import { z } from "zod";

const envSchema = z.object({
  MINIFLUX_API_BASE_URL: z.string().url(),
  MINIFLUX_USERNAME: z.string().min(1),
  MINIFLUX_PASSWORD: z.string().min(1),
  SCORING_DATABASE_URL: z.string().min(1),
  READER_MINIFLUX_USER_ID: z.coerce.number().int().positive(),
  READER_TENANT_ID: z.string().default("default"),
  MINIMAX_API_KEY: z.string().optional(),
  MINIMAX_BASE_URL: z.string().url().optional(),
  MINIMAX_MODEL: z.string().optional(),
  WEB_SEARCH_PROVIDER: z.enum(["none", "brave"]).default("none"),
  WEB_SEARCH_API_KEY: z.string().optional(),
});

export function getConfig() {
  return envSchema.parse(process.env);
}
