import { httpTransit } from "$lib/adapters/http/httpTransit";
import { provideTransit } from "$lib/ui/context";

/** Call once from the root layout, during component initialisation. */
export function provideServices(): void {
  provideTransit(httpTransit());
}
