export async function fetcher<T = any>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Request failed with ${res.status}`);
  }
  return (await res.json()) as T;
}
