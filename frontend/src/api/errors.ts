export type ApiError=Readonly<{kind:'aborted'|'network'|'http'|'invalid-contract'|'no-release';message:string;status?:number}>;
