/**
 * Single entry point for talking to the backend.
 *
 * Components never call fetch directly — they go through here, so auth
 * headers, error shaping, and the base URL live in exactly one place.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    throw new ApiError(`Request to ${path} failed`, response.status);
  }

  return response.json() as Promise<T>;
}

export type HealthResponse = {
  status: string;
  environment: string;
};

export const getHealth = () => apiFetch<HealthResponse>("/health");
