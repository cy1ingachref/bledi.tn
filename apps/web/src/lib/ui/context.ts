import { createContext } from "svelte";
import type { TransitService } from "$lib/application/transitService";

export const [useTransit, provideTransit] = createContext<TransitService>();
