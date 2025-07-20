export async function fetcher<T = any>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    throw new Error(`Request failed with ${res.status}`);
  }
  return (await res.json()) as T;
}
