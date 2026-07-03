/// <reference types="vite/client" />

declare module '@icons-pack/react-simple-icons' {
  import type { ComponentType, SVGProps } from 'react'
  type SI = ComponentType<SVGProps<SVGSVGElement>>
  export const SiApple: SI
  export const SiBilibili: SI
  export const SiDiscord: SI
  export const SiGmail: SI
  export const SiHomeassistant: SI
  export const SiMatrix: SI
  export const SiMattermost: SI
  export const SiQq: SI
  export const SiSignal: SI
  export const SiTelegram: SI
  export const SiWechat: SI
  export const SiWhatsapp: SI
}

declare module '@tabler/icons-react' {
  import type { FC, SVGProps } from 'react'
  export interface IconProps extends SVGProps<SVGSVGElement> {
    size?: number | string
    stroke?: number | string
  }
  export type Icon = FC<IconProps>
  export declare const IconActivity: Icon
  export declare const IconAdjustmentsHorizontal: Icon
  export declare const IconAlertCircle: Icon
  export declare const IconAlertTriangle: Icon
  export declare const IconArchive: Icon
  export declare const IconArchiveOff: Icon
  export declare const IconArrowUp: Icon
  export declare const IconArrowUpRight: Icon
  export declare const IconAt: Icon
  export declare const IconBell: Icon
  export declare const IconBolt: Icon
  export declare const IconBoltFilled: Icon
  export declare const IconBookmark: Icon
  export declare const IconBookmarkFilled: Icon
  export declare const IconBrain: Icon
  export declare const IconBug: Icon
  export declare const IconChartBar: Icon
  export declare const IconCheck: Icon
  export declare const IconChevronDown: Icon
  export declare const IconChevronLeft: Icon
  export declare const IconChevronRight: Icon
  export declare const IconCircle: Icon
  export declare const IconCircleCheck: Icon
  export declare const IconClipboard: Icon
  export declare const IconClock: Icon
  export declare const IconCommand: Icon
  export declare const IconCopy: Icon
  export declare const IconCpu: Icon
  export declare const IconDeviceDesktop: Icon
  export declare const IconDeviceDesktopAnalytics: Icon
  export declare const IconDeviceFloppy: Icon
  export declare const IconDots: Icon
  export declare const IconDotsVertical: Icon
  export declare const IconDownload: Icon
  export declare const IconEgg: Icon
  export declare const IconExternalLink: Icon
  export declare const IconEye: Icon
  export declare const IconEyeOff: Icon
  export declare const IconFileText: Icon
  export declare const IconFolderOpen: Icon
  export declare const IconGitBranch: Icon
  export declare const IconGlobe: Icon
  export declare const IconHash: Icon
  export declare const IconHelpCircle: Icon
  export declare const IconInfoCircle: Icon
  export declare const IconKey: Icon
  export declare const IconLayersIntersect2: Icon
  export declare const IconLayoutBottombar: Icon
  export declare const IconLayoutDashboard: Icon
  export declare const IconLayoutSidebar: Icon
  export declare const IconLink: Icon
  export declare const IconLoader2: Icon
  export declare const IconLock: Icon
  export declare const IconLogin: Icon
  export declare const IconMail: Icon
  export declare const IconMaximize: Icon
  export declare const IconMessage2: Icon
  export declare const IconMessageCircle: Icon
  export declare const IconMessageQuestion: Icon
  export declare const IconMicrophone: Icon
  export declare const IconMicrophoneOff: Icon
  export declare const IconMinimize: Icon
  export declare const IconMoon: Icon
  export declare const IconNotebook: Icon
  export declare const IconPackage: Icon
  export declare const IconPalette: Icon
  export declare const IconPaw: Icon
  export declare const IconPencil: Icon
  export declare const IconPhoto: Icon
  export declare const IconPin: Icon
  export declare const IconPlayerPause: Icon
  export declare const IconPlayerPlay: Icon
  export declare const IconPlayerStop: Icon
  export declare const IconPlayerStopFilled: Icon
  export declare const IconPlus: Icon
  export declare const IconRefresh: Icon
  export declare const IconSearch: Icon
  export declare const IconSend: Icon
  export declare const IconSettings: Icon
  export declare const IconSettings2: Icon
  export declare const IconSquare: Icon
  export declare const IconSteeringWheel: Icon
  export declare const IconSun: Icon
  export declare const IconTerminal2: Icon
  export declare const IconTool: Icon
  export declare const IconTrash: Icon
  export declare const IconUpload: Icon
  export declare const IconUsers: Icon
  export declare const IconVolume2: Icon
  export declare const IconVolumeOff: Icon
  export declare const IconWaveSine: Icon
  export declare const IconX: Icon
  export declare const IconZoomIn: Icon
  export declare const IconZoomOut: Icon
}
