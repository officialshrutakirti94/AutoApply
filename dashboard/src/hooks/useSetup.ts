import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Preference, type Profile } from "@/lib/api";

/**
 * Autosave for the setup form.
 *
 * 600 ms debounce, and the "Saved" pill only appears once the server has actually
 * acknowledged the write. Never blocks navigation: the user can keep typing while a
 * save is in flight, and the last value always wins.
 */
export function useAutosave() {
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const pending = useRef(0);

  const run = useCallback(async (key: string, work: () => Promise<unknown>) => {
    pending.current += 1;
    setState("saving");
    try {
      await work();
      pending.current -= 1;
      if (pending.current === 0) {
        setState("saved");
        setTimeout(() => {
          if (pending.current === 0) setState("idle");
        }, 1600);
      }
    } catch {
      pending.current -= 1;
      setState("error");
    }
    clearTimeout(timers.current[key]);
  }, []);

  const queue = useCallback(
    (key: string, work: () => Promise<unknown>) => {
      clearTimeout(timers.current[key]);
      timers.current[key] = setTimeout(() => void run(key, work), 600);
    },
    [run],
  );

  const flush = useCallback(
    (key: string, work: () => Promise<unknown>) => {
      clearTimeout(timers.current[key]);
      return run(key, work);
    },
    [run],
  );

  const cancel = useCallback(() => {
    Object.values(timers.current).forEach(clearTimeout);
    timers.current = {};
  }, []);

  useEffect(() => {
    const current = timers.current;
    return () => Object.values(current).forEach(clearTimeout);
  }, []);

  return { state, queue, flush, cancel };
}

/**
 * Setup state.
 *
 * Hydration is per slice and gated on whether the user has edited that slice. The
 * gating matters: the resume parse rewrites the profile on the server, and without
 * it the prefilled values never reach the form because the first hydration already
 * happened. `clearDirty()` is what lets a fresh parse take over again.
 */
export function useSetupState() {
  const queryClient = useQueryClient();

  const profileQuery = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const preferencesQuery = useQuery({ queryKey: ["preferences"], queryFn: api.preferences });
  const meQuery = useQuery({ queryKey: ["me"], queryFn: api.me });
  const resumeQuery = useQuery({
    queryKey: ["resume"],
    queryFn: api.resumeDraft,
    retry: false,
  });

  const [profile, setProfileState] = useState<Partial<Profile>>({});
  const [preferences, setPreferencesState] = useState<Partial<Preference>>({});
  const dirty = useRef({ profile: false, preferences: false });

  useEffect(() => {
    if (profileQuery.data && !dirty.current.profile) {
      setProfileState(profileQuery.data);
    }
  }, [profileQuery.data]);

  useEffect(() => {
    if (preferencesQuery.data && !dirty.current.preferences) {
      setPreferencesState(preferencesQuery.data);
    }
  }, [preferencesQuery.data]);

  const saveProfile = useMutation({
    mutationFn: (patch: Partial<Profile>) => api.updateProfile(patch),
    onSuccess: (data) => queryClient.setQueryData(["profile"], data),
  });

  const savePreferences = useMutation({
    mutationFn: (patch: Partial<Preference>) => api.updatePreferences(patch),
    onSuccess: (data) => queryClient.setQueryData(["preferences"], data),
  });

  const patchProfile = useCallback((patch: Partial<Profile>) => {
    dirty.current.profile = true;
    setProfileState((current) => ({ ...current, ...patch }));
  }, []);

  const patchPreference = useCallback((patch: Partial<Preference>) => {
    dirty.current.preferences = true;
    setPreferencesState((current) => ({ ...current, ...patch }));
  }, []);

  /** Forget local edits so the next server value hydrates the form again. */
  const clearDirty = useCallback(() => {
    dirty.current = { profile: false, preferences: false };
    if (profileQuery.data) setProfileState(profileQuery.data);
    if (preferencesQuery.data) setPreferencesState(preferencesQuery.data);
  }, [profileQuery.data, preferencesQuery.data]);

  return {
    me: meQuery.data,
    profile,
    preferences,
    resume: resumeQuery.data,
    patchProfile,
    patchPreference,
    clearDirty,
    saveProfile,
    savePreferences,
    isLoading: profileQuery.isLoading || preferencesQuery.isLoading,
    isDirty: dirty,
  };
}