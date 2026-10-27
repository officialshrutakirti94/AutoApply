export {};

declare global {
  interface GoogleCredentialResponse {
    credential: string;
    select_by?: string;
    clientId?: string;
  }

  interface GoogleIdentityServices {
    initialize(config: {
      client_id: string;
      callback: (response: GoogleCredentialResponse) => void;
      auto_select?: boolean;
      cancel_on_tap_outside?: boolean;
      ux_mode?: "popup" | "redirect";
    }): void;
    renderButton(
      parent: HTMLElement,
      options: {
        theme?: "outline" | "filled_blue" | "filled_black";
        size?: "large" | "medium" | "small";
        shape?: "rectangular" | "pill" | "circle" | "square";
        text?: "signin_with" | "signup_with" | "continue_with" | "signin";
        logo_alignment?: "left" | "center";
        width?: number;
        locale?: string;
      },
    ): void;
    disableAutoSelect(): void;
  }

  interface Window {
    google?: { accounts: { id: GoogleIdentityServices } };
  }
}