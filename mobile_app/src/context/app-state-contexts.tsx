import { createContext, type PropsWithChildren, useContext } from "react";
import type { AppContextValue } from "@/context/app-context";

export type SessionState = Pick<
  AppContextValue,
  | "accessDestination"
  | "accessError"
  | "accessSession"
  | "deleteAccount"
  | "deviceApprovalRequired"
  | "hasFirebaseSession"
  | "hasPermission"
  | "isAuthenticated"
  | "isHydrated"
  | "isResolvingAccess"
  | "login"
  | "logout"
  | "refreshAccess"
  | "register"
>;

export type ProfileState = Pick<AppContextValue, "profile" | "updateProfile">;

export type PreferencesState = Pick<
  AppContextValue,
  "favorites" | "markCouponUsed" | "toggleFavorite" | "usedCoupons"
>;

export type PublicCacheState = Pick<
  AppContextValue,
  | "createPost"
  | "deletePost"
  | "refreshUnreadMessageCount"
  | "unreadMessageCount"
  | "updatePost"
  | "userPosts"
>;

const SessionContext = createContext<SessionState | null>(null);
const ProfileContext = createContext<ProfileState | null>(null);
const PreferencesContext = createContext<PreferencesState | null>(null);
const PublicCacheContext = createContext<PublicCacheState | null>(null);

type AppStateProvidersProps = PropsWithChildren<{
  preferences: PreferencesState;
  profile: ProfileState;
  publicCache: PublicCacheState;
  session: SessionState;
}>;

export function AppStateProviders({ children, preferences, profile, publicCache, session }: AppStateProvidersProps) {
  return (
    <SessionContext.Provider value={session}>
      <ProfileContext.Provider value={profile}>
        <PreferencesContext.Provider value={preferences}>
          <PublicCacheContext.Provider value={publicCache}>
            {children}
          </PublicCacheContext.Provider>
        </PreferencesContext.Provider>
      </ProfileContext.Provider>
    </SessionContext.Provider>
  );
}

function requiredContext<T>(value: T | null, hookName: string) {
  if (!value) throw new Error(`${hookName} deve ser utilizado dentro de AppProvider.`);
  return value;
}

export function useSessionState() {
  return requiredContext(useContext(SessionContext), "useSessionState");
}

export function useProfileState() {
  return requiredContext(useContext(ProfileContext), "useProfileState");
}

export function usePreferencesState() {
  return requiredContext(useContext(PreferencesContext), "usePreferencesState");
}

export function usePublicCacheState() {
  return requiredContext(useContext(PublicCacheContext), "usePublicCacheState");
}
