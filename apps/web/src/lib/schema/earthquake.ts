import { z } from "zod";

export const earthquakeSchema = z.object({
  magnitude: z.number().min(6.5, "La magnitud mínima es 6.5 Mw"),
  depth: z.number().min(0, "La profundidad no puede ser negativa"),
  latitude: z.number().min(-90).max(90, "La latitud debe estar entre -90 y 90"),
  longitude: z.number().min(-180).max(180, "La longitud debe estar entre -180 y 180"),
  datetime: z.string().min(1, "Indique la fecha y hora del evento"),
});

export type EarthquakeForm = z.infer<typeof earthquakeSchema>;

export interface EarthquakeInput {
  Mw: number;
  h: number;
  lat0: number;
  lon0: number;
  dia: string;
  hhmm: string;
}

/** The compute API expects event day and time in UTC fields. */
export function toEarthquakeInput(values: EarthquakeForm): EarthquakeInput {
  const when = new Date(values.datetime);
  const dia = String(when.getUTCDate()).padStart(2, "0");
  const hhmm =
    String(when.getUTCHours()).padStart(2, "0") + String(when.getUTCMinutes()).padStart(2, "0");
  return {
    Mw: values.magnitude,
    h: values.depth,
    lat0: values.latitude,
    lon0: values.longitude,
    dia,
    hhmm,
  };
}

export const defaultEarthquake: EarthquakeForm = {
  magnitude: 7.5,
  depth: 10,
  latitude: -20.5,
  longitude: -70.5,
  datetime: new Date().toISOString().slice(0, 16),
};
