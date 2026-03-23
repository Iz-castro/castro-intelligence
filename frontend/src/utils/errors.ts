import { ApiError } from "../api";

export function errorText(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Erro inesperado";
}
