import { type ComponentProps } from "solid-js"
import luisPurpuLogo from "../assets/luis-purpu-logo.png"

export const Mark = (props: { class?: string }) => {
  return (
    <svg
      data-component="logo-mark"
      classList={{ [props.class ?? ""]: !!props.class }}
      viewBox="0 0 16 20"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path data-slot="logo-logo-mark-shadow" d="M12 16H4V8H12V16Z" fill="var(--icon-weak-base)" />
      <path data-slot="logo-logo-mark-o" d="M12 4H4V16H12V4ZM16 20H0V0H16V20Z" fill="var(--icon-strong-base)" />
    </svg>
  )
}

export const Splash = (props: Pick<ComponentProps<"img">, "ref" | "class">) => {
  return (
    <img
      ref={props.ref}
      data-component="logo-splash"
      classList={{ [props.class ?? ""]: !!props.class }}
      src={luisPurpuLogo}
      alt="LUIS-PURPU"
      draggable={false}
    >
    </img>
  )
}

export const Logo = (props: { class?: string }) => {
  return (
    <img
      classList={{ [props.class ?? ""]: !!props.class }}
      src={luisPurpuLogo}
      alt="LUIS-PURPU"
      draggable={false}
    />
  )
}
