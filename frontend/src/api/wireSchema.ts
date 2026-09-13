import {z} from 'zod';
export const locationSchema=z.object({id:z.string().regex(/^syn-/),name:z.string(),region:z.string(),category:z.string(),lat:z.number().nullable(),lon:z.number().nullable(),observed:z.string(),source:z.string()});
export const envelopeSchema=z.object({data:z.array(locationSchema),meta:z.object({release:z.string(),profile:z.enum(['curated','community'])})});
export type WireEnvelope=z.infer<typeof envelopeSchema>;
