export type ApiError=Readonly<{kind:'aborted'|'network'|'http'|'invalid-contract'|'no-release'|'unavailable'|'restricted'|'rate-limited';message:string;status?:number;code?:string}>;
