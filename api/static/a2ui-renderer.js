(()=>{var xn=Object.create;var fs=Object.defineProperty;var wn=Object.getOwnPropertyDescriptor;var $n=Object.getOwnPropertyNames;var Sn=Object.getPrototypeOf,Cn=Object.prototype.hasOwnProperty;var kn=(t=>typeof require<"u"?require:typeof Proxy<"u"?new Proxy(t,{get:(e,r)=>(typeof require<"u"?require:e)[r]}):t)(function(t){if(typeof require<"u")return require.apply(this,arguments);throw Error('Dynamic require of "'+t+'" is not supported')});var Ht=(t,e)=>{for(var r in e)fs(t,r,{get:e[r],enumerable:!0})},Tn=(t,e,r,s)=>{if(e&&typeof e=="object"||typeof e=="function")for(let i of $n(e))!Cn.call(t,i)&&i!==r&&fs(t,i,{get:()=>e[i],enumerable:!(s=wn(e,i))||s.enumerable});return t};var En=(t,e,r)=>(r=t!=null?xn(Sn(t)):{},Tn(e||!t||!t.__esModule?fs(r,"default",{value:t,enumerable:!0}):r,t));var An={bubbles:!0,cancelable:!0,composed:!0},kr=class t extends CustomEvent{static{this.eventName="a2uiaction"}constructor(e){super(t.eventName,{detail:e,...An}),this.payload=e}};var Ds={};Ht(Ds,{isComponentArrayReference:()=>gs,isObject:()=>Z,isPath:()=>ms,isResolvedAudioPlayer:()=>ys,isResolvedButton:()=>vs,isResolvedCard:()=>_s,isResolvedCheckbox:()=>bs,isResolvedColumn:()=>xs,isResolvedDateTimeInput:()=>ws,isResolvedDivider:()=>$s,isResolvedIcon:()=>Cs,isResolvedImage:()=>Ss,isResolvedList:()=>ks,isResolvedModal:()=>Ts,isResolvedMultipleChoice:()=>Es,isResolvedRow:()=>As,isResolvedSlider:()=>Is,isResolvedTabs:()=>Rs,isResolvedText:()=>Os,isResolvedTextField:()=>js,isResolvedVideo:()=>Ps,isValueMap:()=>Rn});function Rn(t){return Z(t)&&"key"in t}function ms(t,e){return t==="path"&&typeof e=="string"}function Z(t){return typeof t=="object"&&t!==null&&!Array.isArray(t)}function gs(t){return Z(t)?"explicitList"in t||"template"in t:!1}function Ae(t){return Z(t)&&("path"in t||"literal"in t&&typeof t.literal=="string"||"literalString"in t)}function On(t){return Z(t)&&("path"in t||"literal"in t&&typeof t.literal=="number"||"literalNumber"in t)}function jn(t){return Z(t)&&("path"in t||"literal"in t&&typeof t.literal=="boolean"||"literalBoolean"in t)}function Ee(t){return!(!Z(t)||!("id"in t&&"type"in t&&"properties"in t))}function ys(t){return Z(t)&&"url"in t&&Ae(t.url)}function vs(t){return Z(t)&&"child"in t&&Ee(t.child)&&"action"in t}function _s(t){return Z(t)?"child"in t?Ee(t.child):"children"in t?Array.isArray(t.children)&&t.children.every(Ee):!1:!1}function bs(t){return Z(t)&&"label"in t&&Ae(t.label)&&"value"in t&&jn(t.value)}function xs(t){return Z(t)&&"children"in t&&Array.isArray(t.children)&&t.children.every(Ee)}function ws(t){return Z(t)&&"value"in t&&Ae(t.value)}function $s(t){return Z(t)}function Ss(t){return Z(t)&&"url"in t&&Ae(t.url)}function Cs(t){return Z(t)&&"name"in t&&Ae(t.name)}function ks(t){return Z(t)&&"children"in t&&Array.isArray(t.children)&&t.children.every(Ee)}function Ts(t){return Z(t)&&"entryPointChild"in t&&Ee(t.entryPointChild)&&"contentChild"in t&&Ee(t.contentChild)}function Es(t){return Z(t)&&"selections"in t}function As(t){return Z(t)&&"children"in t&&Array.isArray(t.children)&&t.children.every(Ee)}function Is(t){return Z(t)&&"value"in t&&On(t.value)}function Pn(t){return Z(t)&&"title"in t&&Ae(t.title)&&"child"in t&&Ee(t.child)}function Rs(t){return Z(t)&&"tabItems"in t&&Array.isArray(t.tabItems)&&t.tabItems.every(Pn)}function Os(t){return Z(t)&&"text"in t&&Ae(t.text)}function js(t){return Z(t)&&"label"in t&&Ae(t.label)}function Ps(t){return Z(t)&&"url"in t&&Ae(t.url)}var Er={};Ht(Er,{A2UIValidationEvent:()=>Tr});var Tr=class t extends CustomEvent{constructor(e,r){super(t.EVENT_NAME,{bubbles:!0,composed:!0,...r,detail:{...e,eventType:t.EVENT_NAME}})}};Tr.EVENT_NAME="a2ui-validation-input";var x={};Ht(x,{BRAND:()=>no,DIRTY:()=>Qe,EMPTY_PATH:()=>zn,INVALID:()=>j,NEVER:()=>qo,OK:()=>ae,ParseStatus:()=>re,Schema:()=>V,ZodAny:()=>Ze,ZodArray:()=>je,ZodBigInt:()=>tt,ZodBoolean:()=>rt,ZodBranded:()=>Wt,ZodCatch:()=>pt,ZodDate:()=>st,ZodDefault:()=>ht,ZodDiscriminatedUnion:()=>Rr,ZodEffects:()=>me,ZodEnum:()=>ut,ZodError:()=>le,ZodFirstPartyTypeKind:()=>P,ZodFunction:()=>jr,ZodIntersection:()=>ot,ZodIssueCode:()=>$,ZodLazy:()=>lt,ZodLiteral:()=>ct,ZodMap:()=>It,ZodNaN:()=>Ot,ZodNativeEnum:()=>dt,ZodNever:()=>_e,ZodNull:()=>at,ZodNullable:()=>Se,ZodNumber:()=>et,ZodObject:()=>ce,ZodOptional:()=>pe,ZodParsedType:()=>E,ZodPipeline:()=>Zt,ZodPromise:()=>Ge,ZodReadonly:()=>ft,ZodRecord:()=>Or,ZodSchema:()=>V,ZodSet:()=>Rt,ZodString:()=>We,ZodSymbol:()=>Et,ZodTransformer:()=>me,ZodTuple:()=>$e,ZodType:()=>V,ZodUndefined:()=>it,ZodUnion:()=>nt,ZodUnknown:()=>Oe,ZodVoid:()=>At,addIssueToContext:()=>T,any:()=>go,array:()=>bo,bigint:()=>uo,boolean:()=>Ki,coerce:()=>Ho,custom:()=>Zi,date:()=>ho,datetimeRegex:()=>qi,defaultErrorMap:()=>Ie,discriminatedUnion:()=>So,effect:()=>No,enum:()=>jo,function:()=>Io,getErrorMap:()=>Ct,getParsedType:()=>we,instanceof:()=>lo,intersection:()=>Co,isAborted:()=>Ar,isAsync:()=>kt,isDirty:()=>Ir,isValid:()=>qe,late:()=>oo,lazy:()=>Ro,literal:()=>Oo,makeIssue:()=>qt,map:()=>Eo,nan:()=>co,nativeEnum:()=>Po,never:()=>vo,null:()=>mo,nullable:()=>zo,number:()=>Xi,object:()=>xo,objectUtil:()=>Ns,oboolean:()=>Bo,onumber:()=>Fo,optional:()=>Mo,ostring:()=>Lo,pipeline:()=>Uo,preprocess:()=>Vo,promise:()=>Do,quotelessJson:()=>Dn,record:()=>To,set:()=>Ao,setErrorMap:()=>Mn,strictObject:()=>wo,string:()=>Gi,symbol:()=>po,transformer:()=>No,tuple:()=>ko,undefined:()=>fo,union:()=>$o,unknown:()=>yo,util:()=>H,void:()=>_o});var H;(function(t){t.assertEqual=i=>{};function e(i){}t.assertIs=e;function r(i){throw new Error}t.assertNever=r,t.arrayToEnum=i=>{let a={};for(let n of i)a[n]=n;return a},t.getValidEnumValues=i=>{let a=t.objectKeys(i).filter(o=>typeof i[i[o]]!="number"),n={};for(let o of a)n[o]=i[o];return t.objectValues(n)},t.objectValues=i=>t.objectKeys(i).map(function(a){return i[a]}),t.objectKeys=typeof Object.keys=="function"?i=>Object.keys(i):i=>{let a=[];for(let n in i)Object.prototype.hasOwnProperty.call(i,n)&&a.push(n);return a},t.find=(i,a)=>{for(let n of i)if(a(n))return n},t.isInteger=typeof Number.isInteger=="function"?i=>Number.isInteger(i):i=>typeof i=="number"&&Number.isFinite(i)&&Math.floor(i)===i;function s(i,a=" | "){return i.map(n=>typeof n=="string"?`'${n}'`:n).join(a)}t.joinValues=s,t.jsonStringifyReplacer=(i,a)=>typeof a=="bigint"?a.toString():a})(H||(H={}));var Ns;(function(t){t.mergeShapes=(e,r)=>({...e,...r})})(Ns||(Ns={}));var E=H.arrayToEnum(["string","nan","number","integer","float","boolean","date","bigint","symbol","function","undefined","null","array","object","unknown","promise","void","never","map","set"]),we=t=>{switch(typeof t){case"undefined":return E.undefined;case"string":return E.string;case"number":return Number.isNaN(t)?E.nan:E.number;case"boolean":return E.boolean;case"function":return E.function;case"bigint":return E.bigint;case"symbol":return E.symbol;case"object":return Array.isArray(t)?E.array:t===null?E.null:t.then&&typeof t.then=="function"&&t.catch&&typeof t.catch=="function"?E.promise:typeof Map<"u"&&t instanceof Map?E.map:typeof Set<"u"&&t instanceof Set?E.set:typeof Date<"u"&&t instanceof Date?E.date:E.object;default:return E.unknown}};var $=H.arrayToEnum(["invalid_type","invalid_literal","custom","invalid_union","invalid_union_discriminator","invalid_enum_value","unrecognized_keys","invalid_arguments","invalid_return_type","invalid_date","invalid_string","too_small","too_big","invalid_intersection_types","not_multiple_of","not_finite"]),Dn=t=>JSON.stringify(t,null,2).replace(/"([^"]+)":/g,"$1:"),le=class t extends Error{get errors(){return this.issues}constructor(e){super(),this.issues=[],this.addIssue=s=>{this.issues=[...this.issues,s]},this.addIssues=(s=[])=>{this.issues=[...this.issues,...s]};let r=new.target.prototype;Object.setPrototypeOf?Object.setPrototypeOf(this,r):this.__proto__=r,this.name="ZodError",this.issues=e}format(e){let r=e||function(a){return a.message},s={_errors:[]},i=a=>{for(let n of a.issues)if(n.code==="invalid_union")n.unionErrors.map(i);else if(n.code==="invalid_return_type")i(n.returnTypeError);else if(n.code==="invalid_arguments")i(n.argumentsError);else if(n.path.length===0)s._errors.push(r(n));else{let o=s,d=0;for(;d<n.path.length;){let u=n.path[d];d===n.path.length-1?(o[u]=o[u]||{_errors:[]},o[u]._errors.push(r(n))):o[u]=o[u]||{_errors:[]},o=o[u],d++}}};return i(this),s}static assert(e){if(!(e instanceof t))throw new Error(`Not a ZodError: ${e}`)}toString(){return this.message}get message(){return JSON.stringify(this.issues,H.jsonStringifyReplacer,2)}get isEmpty(){return this.issues.length===0}flatten(e=r=>r.message){let r={},s=[];for(let i of this.issues)if(i.path.length>0){let a=i.path[0];r[a]=r[a]||[],r[a].push(e(i))}else s.push(e(i));return{formErrors:s,fieldErrors:r}}get formErrors(){return this.flatten()}};le.create=t=>new le(t);var Nn=(t,e)=>{let r;switch(t.code){case $.invalid_type:t.received===E.undefined?r="Required":r=`Expected ${t.expected}, received ${t.received}`;break;case $.invalid_literal:r=`Invalid literal value, expected ${JSON.stringify(t.expected,H.jsonStringifyReplacer)}`;break;case $.unrecognized_keys:r=`Unrecognized key(s) in object: ${H.joinValues(t.keys,", ")}`;break;case $.invalid_union:r="Invalid input";break;case $.invalid_union_discriminator:r=`Invalid discriminator value. Expected ${H.joinValues(t.options)}`;break;case $.invalid_enum_value:r=`Invalid enum value. Expected ${H.joinValues(t.options)}, received '${t.received}'`;break;case $.invalid_arguments:r="Invalid function arguments";break;case $.invalid_return_type:r="Invalid function return type";break;case $.invalid_date:r="Invalid date";break;case $.invalid_string:typeof t.validation=="object"?"includes"in t.validation?(r=`Invalid input: must include "${t.validation.includes}"`,typeof t.validation.position=="number"&&(r=`${r} at one or more positions greater than or equal to ${t.validation.position}`)):"startsWith"in t.validation?r=`Invalid input: must start with "${t.validation.startsWith}"`:"endsWith"in t.validation?r=`Invalid input: must end with "${t.validation.endsWith}"`:H.assertNever(t.validation):t.validation!=="regex"?r=`Invalid ${t.validation}`:r="Invalid";break;case $.too_small:t.type==="array"?r=`Array must contain ${t.exact?"exactly":t.inclusive?"at least":"more than"} ${t.minimum} element(s)`:t.type==="string"?r=`String must contain ${t.exact?"exactly":t.inclusive?"at least":"over"} ${t.minimum} character(s)`:t.type==="number"?r=`Number must be ${t.exact?"exactly equal to ":t.inclusive?"greater than or equal to ":"greater than "}${t.minimum}`:t.type==="bigint"?r=`Number must be ${t.exact?"exactly equal to ":t.inclusive?"greater than or equal to ":"greater than "}${t.minimum}`:t.type==="date"?r=`Date must be ${t.exact?"exactly equal to ":t.inclusive?"greater than or equal to ":"greater than "}${new Date(Number(t.minimum))}`:r="Invalid input";break;case $.too_big:t.type==="array"?r=`Array must contain ${t.exact?"exactly":t.inclusive?"at most":"less than"} ${t.maximum} element(s)`:t.type==="string"?r=`String must contain ${t.exact?"exactly":t.inclusive?"at most":"under"} ${t.maximum} character(s)`:t.type==="number"?r=`Number must be ${t.exact?"exactly":t.inclusive?"less than or equal to":"less than"} ${t.maximum}`:t.type==="bigint"?r=`BigInt must be ${t.exact?"exactly":t.inclusive?"less than or equal to":"less than"} ${t.maximum}`:t.type==="date"?r=`Date must be ${t.exact?"exactly":t.inclusive?"smaller than or equal to":"smaller than"} ${new Date(Number(t.maximum))}`:r="Invalid input";break;case $.custom:r="Invalid input";break;case $.invalid_intersection_types:r="Intersection results could not be merged";break;case $.not_multiple_of:r=`Number must be a multiple of ${t.multipleOf}`;break;case $.not_finite:r="Number must be finite";break;default:r=e.defaultError,H.assertNever(t)}return{message:r}},Ie=Nn;var Ui=Ie;function Mn(t){Ui=t}function Ct(){return Ui}var qt=t=>{let{data:e,path:r,errorMaps:s,issueData:i}=t,a=[...r,...i.path||[]],n={...i,path:a};if(i.message!==void 0)return{...i,path:a,message:i.message};let o="",d=s.filter(u=>!!u).slice().reverse();for(let u of d)o=u(n,{data:e,defaultError:o}).message;return{...i,path:a,message:o}},zn=[];function T(t,e){let r=Ct(),s=qt({issueData:e,data:t.data,path:t.path,errorMaps:[t.common.contextualErrorMap,t.schemaErrorMap,r,r===Ie?void 0:Ie].filter(i=>!!i)});t.common.issues.push(s)}var re=class t{constructor(){this.value="valid"}dirty(){this.value==="valid"&&(this.value="dirty")}abort(){this.value!=="aborted"&&(this.value="aborted")}static mergeArray(e,r){let s=[];for(let i of r){if(i.status==="aborted")return j;i.status==="dirty"&&e.dirty(),s.push(i.value)}return{status:e.value,value:s}}static async mergeObjectAsync(e,r){let s=[];for(let i of r){let a=await i.key,n=await i.value;s.push({key:a,value:n})}return t.mergeObjectSync(e,s)}static mergeObjectSync(e,r){let s={};for(let i of r){let{key:a,value:n}=i;if(a.status==="aborted"||n.status==="aborted")return j;a.status==="dirty"&&e.dirty(),n.status==="dirty"&&e.dirty(),a.value!=="__proto__"&&(typeof n.value<"u"||i.alwaysSet)&&(s[a.value]=n.value)}return{status:e.value,value:s}}},j=Object.freeze({status:"aborted"}),Qe=t=>({status:"dirty",value:t}),ae=t=>({status:"valid",value:t}),Ar=t=>t.status==="aborted",Ir=t=>t.status==="dirty",qe=t=>t.status==="valid",kt=t=>typeof Promise<"u"&&t instanceof Promise;var I;(function(t){t.errToObj=e=>typeof e=="string"?{message:e}:e||{},t.toString=e=>typeof e=="string"?e:e?.message})(I||(I={}));var fe=class{constructor(e,r,s,i){this._cachedPath=[],this.parent=e,this.data=r,this._path=s,this._key=i}get path(){return this._cachedPath.length||(Array.isArray(this._key)?this._cachedPath.push(...this._path,...this._key):this._cachedPath.push(...this._path,this._key)),this._cachedPath}},Li=(t,e)=>{if(qe(e))return{success:!0,data:e.value};if(!t.common.issues.length)throw new Error("Validation failed but no issues detected.");return{success:!1,get error(){if(this._error)return this._error;let r=new le(t.common.issues);return this._error=r,this._error}}};function M(t){if(!t)return{};let{errorMap:e,invalid_type_error:r,required_error:s,description:i}=t;if(e&&(r||s))throw new Error(`Can't use "invalid_type_error" or "required_error" in conjunction with custom error map.`);return e?{errorMap:e,description:i}:{errorMap:(n,o)=>{let{message:d}=t;return n.code==="invalid_enum_value"?{message:d??o.defaultError}:typeof o.data>"u"?{message:d??s??o.defaultError}:n.code!=="invalid_type"?{message:o.defaultError}:{message:d??r??o.defaultError}},description:i}}var V=class{get description(){return this._def.description}_getType(e){return we(e.data)}_getOrReturnCtx(e,r){return r||{common:e.parent.common,data:e.data,parsedType:we(e.data),schemaErrorMap:this._def.errorMap,path:e.path,parent:e.parent}}_processInputParams(e){return{status:new re,ctx:{common:e.parent.common,data:e.data,parsedType:we(e.data),schemaErrorMap:this._def.errorMap,path:e.path,parent:e.parent}}}_parseSync(e){let r=this._parse(e);if(kt(r))throw new Error("Synchronous parse encountered promise.");return r}_parseAsync(e){let r=this._parse(e);return Promise.resolve(r)}parse(e,r){let s=this.safeParse(e,r);if(s.success)return s.data;throw s.error}safeParse(e,r){let s={common:{issues:[],async:r?.async??!1,contextualErrorMap:r?.errorMap},path:r?.path||[],schemaErrorMap:this._def.errorMap,parent:null,data:e,parsedType:we(e)},i=this._parseSync({data:e,path:s.path,parent:s});return Li(s,i)}"~validate"(e){let r={common:{issues:[],async:!!this["~standard"].async},path:[],schemaErrorMap:this._def.errorMap,parent:null,data:e,parsedType:we(e)};if(!this["~standard"].async)try{let s=this._parseSync({data:e,path:[],parent:r});return qe(s)?{value:s.value}:{issues:r.common.issues}}catch(s){s?.message?.toLowerCase()?.includes("encountered")&&(this["~standard"].async=!0),r.common={issues:[],async:!0}}return this._parseAsync({data:e,path:[],parent:r}).then(s=>qe(s)?{value:s.value}:{issues:r.common.issues})}async parseAsync(e,r){let s=await this.safeParseAsync(e,r);if(s.success)return s.data;throw s.error}async safeParseAsync(e,r){let s={common:{issues:[],contextualErrorMap:r?.errorMap,async:!0},path:r?.path||[],schemaErrorMap:this._def.errorMap,parent:null,data:e,parsedType:we(e)},i=this._parse({data:e,path:s.path,parent:s}),a=await(kt(i)?i:Promise.resolve(i));return Li(s,a)}refine(e,r){let s=i=>typeof r=="string"||typeof r>"u"?{message:r}:typeof r=="function"?r(i):r;return this._refinement((i,a)=>{let n=e(i),o=()=>a.addIssue({code:$.custom,...s(i)});return typeof Promise<"u"&&n instanceof Promise?n.then(d=>d?!0:(o(),!1)):n?!0:(o(),!1)})}refinement(e,r){return this._refinement((s,i)=>e(s)?!0:(i.addIssue(typeof r=="function"?r(s,i):r),!1))}_refinement(e){return new me({schema:this,typeName:P.ZodEffects,effect:{type:"refinement",refinement:e}})}superRefine(e){return this._refinement(e)}constructor(e){this.spa=this.safeParseAsync,this._def=e,this.parse=this.parse.bind(this),this.safeParse=this.safeParse.bind(this),this.parseAsync=this.parseAsync.bind(this),this.safeParseAsync=this.safeParseAsync.bind(this),this.spa=this.spa.bind(this),this.refine=this.refine.bind(this),this.refinement=this.refinement.bind(this),this.superRefine=this.superRefine.bind(this),this.optional=this.optional.bind(this),this.nullable=this.nullable.bind(this),this.nullish=this.nullish.bind(this),this.array=this.array.bind(this),this.promise=this.promise.bind(this),this.or=this.or.bind(this),this.and=this.and.bind(this),this.transform=this.transform.bind(this),this.brand=this.brand.bind(this),this.default=this.default.bind(this),this.catch=this.catch.bind(this),this.describe=this.describe.bind(this),this.pipe=this.pipe.bind(this),this.readonly=this.readonly.bind(this),this.isNullable=this.isNullable.bind(this),this.isOptional=this.isOptional.bind(this),this["~standard"]={version:1,vendor:"zod",validate:r=>this["~validate"](r)}}optional(){return pe.create(this,this._def)}nullable(){return Se.create(this,this._def)}nullish(){return this.nullable().optional()}array(){return je.create(this)}promise(){return Ge.create(this,this._def)}or(e){return nt.create([this,e],this._def)}and(e){return ot.create(this,e,this._def)}transform(e){return new me({...M(this._def),schema:this,typeName:P.ZodEffects,effect:{type:"transform",transform:e}})}default(e){let r=typeof e=="function"?e:()=>e;return new ht({...M(this._def),innerType:this,defaultValue:r,typeName:P.ZodDefault})}brand(){return new Wt({typeName:P.ZodBranded,type:this,...M(this._def)})}catch(e){let r=typeof e=="function"?e:()=>e;return new pt({...M(this._def),innerType:this,catchValue:r,typeName:P.ZodCatch})}describe(e){let r=this.constructor;return new r({...this._def,description:e})}pipe(e){return Zt.create(this,e)}readonly(){return ft.create(this)}isOptional(){return this.safeParse(void 0).success}isNullable(){return this.safeParse(null).success}},Vn=/^c[^\s-]{8,}$/i,Un=/^[0-9a-z]+$/,Ln=/^[0-9A-HJKMNP-TV-Z]{26}$/i,Fn=/^[0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12}$/i,Bn=/^[a-z0-9_-]{21}$/i,Hn=/^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]*$/,qn=/^[-+]?P(?!$)(?:(?:[-+]?\d+Y)|(?:[-+]?\d+[.,]\d+Y$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:(?:[-+]?\d+W)|(?:[-+]?\d+[.,]\d+W$))?(?:(?:[-+]?\d+D)|(?:[-+]?\d+[.,]\d+D$))?(?:T(?=[\d+-])(?:(?:[-+]?\d+H)|(?:[-+]?\d+[.,]\d+H$))?(?:(?:[-+]?\d+M)|(?:[-+]?\d+[.,]\d+M$))?(?:[-+]?\d+(?:[.,]\d+)?S)?)??$/,Wn=/^(?!\.)(?!.*\.\.)([A-Z0-9_'+\-\.]*)[A-Z0-9_+-]@([A-Z0-9][A-Z0-9\-]*\.)+[A-Z]{2,}$/i,Zn="^(\\p{Extended_Pictographic}|\\p{Emoji_Component})+$",Ms,Gn=/^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])$/,Xn=/^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\/(3[0-2]|[12]?[0-9])$/,Kn=/^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$/,Yn=/^(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))\/(12[0-8]|1[01][0-9]|[1-9]?[0-9])$/,Jn=/^([0-9a-zA-Z+/]{4})*(([0-9a-zA-Z+/]{2}==)|([0-9a-zA-Z+/]{3}=))?$/,Qn=/^([0-9a-zA-Z-_]{4})*(([0-9a-zA-Z-_]{2}(==)?)|([0-9a-zA-Z-_]{3}(=)?))?$/,Bi="((\\d\\d[2468][048]|\\d\\d[13579][26]|\\d\\d0[48]|[02468][048]00|[13579][26]00)-02-29|\\d{4}-((0[13578]|1[02])-(0[1-9]|[12]\\d|3[01])|(0[469]|11)-(0[1-9]|[12]\\d|30)|(02)-(0[1-9]|1\\d|2[0-8])))",eo=new RegExp(`^${Bi}$`);function Hi(t){let e="[0-5]\\d";t.precision?e=`${e}\\.\\d{${t.precision}}`:t.precision==null&&(e=`${e}(\\.\\d+)?`);let r=t.precision?"+":"?";return`([01]\\d|2[0-3]):[0-5]\\d(:${e})${r}`}function to(t){return new RegExp(`^${Hi(t)}$`)}function qi(t){let e=`${Bi}T${Hi(t)}`,r=[];return r.push(t.local?"Z?":"Z"),t.offset&&r.push("([+-]\\d{2}:?\\d{2})"),e=`${e}(${r.join("|")})`,new RegExp(`^${e}$`)}function ro(t,e){return!!((e==="v4"||!e)&&Gn.test(t)||(e==="v6"||!e)&&Kn.test(t))}function so(t,e){if(!Hn.test(t))return!1;try{let[r]=t.split(".");if(!r)return!1;let s=r.replace(/-/g,"+").replace(/_/g,"/").padEnd(r.length+(4-r.length%4)%4,"="),i=JSON.parse(atob(s));return!(typeof i!="object"||i===null||"typ"in i&&i?.typ!=="JWT"||!i.alg||e&&i.alg!==e)}catch{return!1}}function io(t,e){return!!((e==="v4"||!e)&&Xn.test(t)||(e==="v6"||!e)&&Yn.test(t))}var We=class t extends V{_parse(e){if(this._def.coerce&&(e.data=String(e.data)),this._getType(e)!==E.string){let a=this._getOrReturnCtx(e);return T(a,{code:$.invalid_type,expected:E.string,received:a.parsedType}),j}let s=new re,i;for(let a of this._def.checks)if(a.kind==="min")e.data.length<a.value&&(i=this._getOrReturnCtx(e,i),T(i,{code:$.too_small,minimum:a.value,type:"string",inclusive:!0,exact:!1,message:a.message}),s.dirty());else if(a.kind==="max")e.data.length>a.value&&(i=this._getOrReturnCtx(e,i),T(i,{code:$.too_big,maximum:a.value,type:"string",inclusive:!0,exact:!1,message:a.message}),s.dirty());else if(a.kind==="length"){let n=e.data.length>a.value,o=e.data.length<a.value;(n||o)&&(i=this._getOrReturnCtx(e,i),n?T(i,{code:$.too_big,maximum:a.value,type:"string",inclusive:!0,exact:!0,message:a.message}):o&&T(i,{code:$.too_small,minimum:a.value,type:"string",inclusive:!0,exact:!0,message:a.message}),s.dirty())}else if(a.kind==="email")Wn.test(e.data)||(i=this._getOrReturnCtx(e,i),T(i,{validation:"email",code:$.invalid_string,message:a.message}),s.dirty());else if(a.kind==="emoji")Ms||(Ms=new RegExp(Zn,"u")),Ms.test(e.data)||(i=this._getOrReturnCtx(e,i),T(i,{validation:"emoji",code:$.invalid_string,message:a.message}),s.dirty());else if(a.kind==="uuid")Fn.test(e.data)||(i=this._getOrReturnCtx(e,i),T(i,{validation:"uuid",code:$.invalid_string,message:a.message}),s.dirty());else if(a.kind==="nanoid")Bn.test(e.data)||(i=this._getOrReturnCtx(e,i),T(i,{validation:"nanoid",code:$.invalid_string,message:a.message}),s.dirty());else if(a.kind==="cuid")Vn.test(e.data)||(i=this._getOrReturnCtx(e,i),T(i,{validation:"cuid",code:$.invalid_string,message:a.message}),s.dirty());else if(a.kind==="cuid2")Un.test(e.data)||(i=this._getOrReturnCtx(e,i),T(i,{validation:"cuid2",code:$.invalid_string,message:a.message}),s.dirty());else if(a.kind==="ulid")Ln.test(e.data)||(i=this._getOrReturnCtx(e,i),T(i,{validation:"ulid",code:$.invalid_string,message:a.message}),s.dirty());else if(a.kind==="url")try{new URL(e.data)}catch{i=this._getOrReturnCtx(e,i),T(i,{validation:"url",code:$.invalid_string,message:a.message}),s.dirty()}else a.kind==="regex"?(a.regex.lastIndex=0,a.regex.test(e.data)||(i=this._getOrReturnCtx(e,i),T(i,{validation:"regex",code:$.invalid_string,message:a.message}),s.dirty())):a.kind==="trim"?e.data=e.data.trim():a.kind==="includes"?e.data.includes(a.value,a.position)||(i=this._getOrReturnCtx(e,i),T(i,{code:$.invalid_string,validation:{includes:a.value,position:a.position},message:a.message}),s.dirty()):a.kind==="toLowerCase"?e.data=e.data.toLowerCase():a.kind==="toUpperCase"?e.data=e.data.toUpperCase():a.kind==="startsWith"?e.data.startsWith(a.value)||(i=this._getOrReturnCtx(e,i),T(i,{code:$.invalid_string,validation:{startsWith:a.value},message:a.message}),s.dirty()):a.kind==="endsWith"?e.data.endsWith(a.value)||(i=this._getOrReturnCtx(e,i),T(i,{code:$.invalid_string,validation:{endsWith:a.value},message:a.message}),s.dirty()):a.kind==="datetime"?qi(a).test(e.data)||(i=this._getOrReturnCtx(e,i),T(i,{code:$.invalid_string,validation:"datetime",message:a.message}),s.dirty()):a.kind==="date"?eo.test(e.data)||(i=this._getOrReturnCtx(e,i),T(i,{code:$.invalid_string,validation:"date",message:a.message}),s.dirty()):a.kind==="time"?to(a).test(e.data)||(i=this._getOrReturnCtx(e,i),T(i,{code:$.invalid_string,validation:"time",message:a.message}),s.dirty()):a.kind==="duration"?qn.test(e.data)||(i=this._getOrReturnCtx(e,i),T(i,{validation:"duration",code:$.invalid_string,message:a.message}),s.dirty()):a.kind==="ip"?ro(e.data,a.version)||(i=this._getOrReturnCtx(e,i),T(i,{validation:"ip",code:$.invalid_string,message:a.message}),s.dirty()):a.kind==="jwt"?so(e.data,a.alg)||(i=this._getOrReturnCtx(e,i),T(i,{validation:"jwt",code:$.invalid_string,message:a.message}),s.dirty()):a.kind==="cidr"?io(e.data,a.version)||(i=this._getOrReturnCtx(e,i),T(i,{validation:"cidr",code:$.invalid_string,message:a.message}),s.dirty()):a.kind==="base64"?Jn.test(e.data)||(i=this._getOrReturnCtx(e,i),T(i,{validation:"base64",code:$.invalid_string,message:a.message}),s.dirty()):a.kind==="base64url"?Qn.test(e.data)||(i=this._getOrReturnCtx(e,i),T(i,{validation:"base64url",code:$.invalid_string,message:a.message}),s.dirty()):H.assertNever(a);return{status:s.value,value:e.data}}_regex(e,r,s){return this.refinement(i=>e.test(i),{validation:r,code:$.invalid_string,...I.errToObj(s)})}_addCheck(e){return new t({...this._def,checks:[...this._def.checks,e]})}email(e){return this._addCheck({kind:"email",...I.errToObj(e)})}url(e){return this._addCheck({kind:"url",...I.errToObj(e)})}emoji(e){return this._addCheck({kind:"emoji",...I.errToObj(e)})}uuid(e){return this._addCheck({kind:"uuid",...I.errToObj(e)})}nanoid(e){return this._addCheck({kind:"nanoid",...I.errToObj(e)})}cuid(e){return this._addCheck({kind:"cuid",...I.errToObj(e)})}cuid2(e){return this._addCheck({kind:"cuid2",...I.errToObj(e)})}ulid(e){return this._addCheck({kind:"ulid",...I.errToObj(e)})}base64(e){return this._addCheck({kind:"base64",...I.errToObj(e)})}base64url(e){return this._addCheck({kind:"base64url",...I.errToObj(e)})}jwt(e){return this._addCheck({kind:"jwt",...I.errToObj(e)})}ip(e){return this._addCheck({kind:"ip",...I.errToObj(e)})}cidr(e){return this._addCheck({kind:"cidr",...I.errToObj(e)})}datetime(e){return typeof e=="string"?this._addCheck({kind:"datetime",precision:null,offset:!1,local:!1,message:e}):this._addCheck({kind:"datetime",precision:typeof e?.precision>"u"?null:e?.precision,offset:e?.offset??!1,local:e?.local??!1,...I.errToObj(e?.message)})}date(e){return this._addCheck({kind:"date",message:e})}time(e){return typeof e=="string"?this._addCheck({kind:"time",precision:null,message:e}):this._addCheck({kind:"time",precision:typeof e?.precision>"u"?null:e?.precision,...I.errToObj(e?.message)})}duration(e){return this._addCheck({kind:"duration",...I.errToObj(e)})}regex(e,r){return this._addCheck({kind:"regex",regex:e,...I.errToObj(r)})}includes(e,r){return this._addCheck({kind:"includes",value:e,position:r?.position,...I.errToObj(r?.message)})}startsWith(e,r){return this._addCheck({kind:"startsWith",value:e,...I.errToObj(r)})}endsWith(e,r){return this._addCheck({kind:"endsWith",value:e,...I.errToObj(r)})}min(e,r){return this._addCheck({kind:"min",value:e,...I.errToObj(r)})}max(e,r){return this._addCheck({kind:"max",value:e,...I.errToObj(r)})}length(e,r){return this._addCheck({kind:"length",value:e,...I.errToObj(r)})}nonempty(e){return this.min(1,I.errToObj(e))}trim(){return new t({...this._def,checks:[...this._def.checks,{kind:"trim"}]})}toLowerCase(){return new t({...this._def,checks:[...this._def.checks,{kind:"toLowerCase"}]})}toUpperCase(){return new t({...this._def,checks:[...this._def.checks,{kind:"toUpperCase"}]})}get isDatetime(){return!!this._def.checks.find(e=>e.kind==="datetime")}get isDate(){return!!this._def.checks.find(e=>e.kind==="date")}get isTime(){return!!this._def.checks.find(e=>e.kind==="time")}get isDuration(){return!!this._def.checks.find(e=>e.kind==="duration")}get isEmail(){return!!this._def.checks.find(e=>e.kind==="email")}get isURL(){return!!this._def.checks.find(e=>e.kind==="url")}get isEmoji(){return!!this._def.checks.find(e=>e.kind==="emoji")}get isUUID(){return!!this._def.checks.find(e=>e.kind==="uuid")}get isNANOID(){return!!this._def.checks.find(e=>e.kind==="nanoid")}get isCUID(){return!!this._def.checks.find(e=>e.kind==="cuid")}get isCUID2(){return!!this._def.checks.find(e=>e.kind==="cuid2")}get isULID(){return!!this._def.checks.find(e=>e.kind==="ulid")}get isIP(){return!!this._def.checks.find(e=>e.kind==="ip")}get isCIDR(){return!!this._def.checks.find(e=>e.kind==="cidr")}get isBase64(){return!!this._def.checks.find(e=>e.kind==="base64")}get isBase64url(){return!!this._def.checks.find(e=>e.kind==="base64url")}get minLength(){let e=null;for(let r of this._def.checks)r.kind==="min"&&(e===null||r.value>e)&&(e=r.value);return e}get maxLength(){let e=null;for(let r of this._def.checks)r.kind==="max"&&(e===null||r.value<e)&&(e=r.value);return e}};We.create=t=>new We({checks:[],typeName:P.ZodString,coerce:t?.coerce??!1,...M(t)});function ao(t,e){let r=(t.toString().split(".")[1]||"").length,s=(e.toString().split(".")[1]||"").length,i=r>s?r:s,a=Number.parseInt(t.toFixed(i).replace(".","")),n=Number.parseInt(e.toFixed(i).replace(".",""));return a%n/10**i}var et=class t extends V{constructor(){super(...arguments),this.min=this.gte,this.max=this.lte,this.step=this.multipleOf}_parse(e){if(this._def.coerce&&(e.data=Number(e.data)),this._getType(e)!==E.number){let a=this._getOrReturnCtx(e);return T(a,{code:$.invalid_type,expected:E.number,received:a.parsedType}),j}let s,i=new re;for(let a of this._def.checks)a.kind==="int"?H.isInteger(e.data)||(s=this._getOrReturnCtx(e,s),T(s,{code:$.invalid_type,expected:"integer",received:"float",message:a.message}),i.dirty()):a.kind==="min"?(a.inclusive?e.data<a.value:e.data<=a.value)&&(s=this._getOrReturnCtx(e,s),T(s,{code:$.too_small,minimum:a.value,type:"number",inclusive:a.inclusive,exact:!1,message:a.message}),i.dirty()):a.kind==="max"?(a.inclusive?e.data>a.value:e.data>=a.value)&&(s=this._getOrReturnCtx(e,s),T(s,{code:$.too_big,maximum:a.value,type:"number",inclusive:a.inclusive,exact:!1,message:a.message}),i.dirty()):a.kind==="multipleOf"?ao(e.data,a.value)!==0&&(s=this._getOrReturnCtx(e,s),T(s,{code:$.not_multiple_of,multipleOf:a.value,message:a.message}),i.dirty()):a.kind==="finite"?Number.isFinite(e.data)||(s=this._getOrReturnCtx(e,s),T(s,{code:$.not_finite,message:a.message}),i.dirty()):H.assertNever(a);return{status:i.value,value:e.data}}gte(e,r){return this.setLimit("min",e,!0,I.toString(r))}gt(e,r){return this.setLimit("min",e,!1,I.toString(r))}lte(e,r){return this.setLimit("max",e,!0,I.toString(r))}lt(e,r){return this.setLimit("max",e,!1,I.toString(r))}setLimit(e,r,s,i){return new t({...this._def,checks:[...this._def.checks,{kind:e,value:r,inclusive:s,message:I.toString(i)}]})}_addCheck(e){return new t({...this._def,checks:[...this._def.checks,e]})}int(e){return this._addCheck({kind:"int",message:I.toString(e)})}positive(e){return this._addCheck({kind:"min",value:0,inclusive:!1,message:I.toString(e)})}negative(e){return this._addCheck({kind:"max",value:0,inclusive:!1,message:I.toString(e)})}nonpositive(e){return this._addCheck({kind:"max",value:0,inclusive:!0,message:I.toString(e)})}nonnegative(e){return this._addCheck({kind:"min",value:0,inclusive:!0,message:I.toString(e)})}multipleOf(e,r){return this._addCheck({kind:"multipleOf",value:e,message:I.toString(r)})}finite(e){return this._addCheck({kind:"finite",message:I.toString(e)})}safe(e){return this._addCheck({kind:"min",inclusive:!0,value:Number.MIN_SAFE_INTEGER,message:I.toString(e)})._addCheck({kind:"max",inclusive:!0,value:Number.MAX_SAFE_INTEGER,message:I.toString(e)})}get minValue(){let e=null;for(let r of this._def.checks)r.kind==="min"&&(e===null||r.value>e)&&(e=r.value);return e}get maxValue(){let e=null;for(let r of this._def.checks)r.kind==="max"&&(e===null||r.value<e)&&(e=r.value);return e}get isInt(){return!!this._def.checks.find(e=>e.kind==="int"||e.kind==="multipleOf"&&H.isInteger(e.value))}get isFinite(){let e=null,r=null;for(let s of this._def.checks){if(s.kind==="finite"||s.kind==="int"||s.kind==="multipleOf")return!0;s.kind==="min"?(r===null||s.value>r)&&(r=s.value):s.kind==="max"&&(e===null||s.value<e)&&(e=s.value)}return Number.isFinite(r)&&Number.isFinite(e)}};et.create=t=>new et({checks:[],typeName:P.ZodNumber,coerce:t?.coerce||!1,...M(t)});var tt=class t extends V{constructor(){super(...arguments),this.min=this.gte,this.max=this.lte}_parse(e){if(this._def.coerce)try{e.data=BigInt(e.data)}catch{return this._getInvalidInput(e)}if(this._getType(e)!==E.bigint)return this._getInvalidInput(e);let s,i=new re;for(let a of this._def.checks)a.kind==="min"?(a.inclusive?e.data<a.value:e.data<=a.value)&&(s=this._getOrReturnCtx(e,s),T(s,{code:$.too_small,type:"bigint",minimum:a.value,inclusive:a.inclusive,message:a.message}),i.dirty()):a.kind==="max"?(a.inclusive?e.data>a.value:e.data>=a.value)&&(s=this._getOrReturnCtx(e,s),T(s,{code:$.too_big,type:"bigint",maximum:a.value,inclusive:a.inclusive,message:a.message}),i.dirty()):a.kind==="multipleOf"?e.data%a.value!==BigInt(0)&&(s=this._getOrReturnCtx(e,s),T(s,{code:$.not_multiple_of,multipleOf:a.value,message:a.message}),i.dirty()):H.assertNever(a);return{status:i.value,value:e.data}}_getInvalidInput(e){let r=this._getOrReturnCtx(e);return T(r,{code:$.invalid_type,expected:E.bigint,received:r.parsedType}),j}gte(e,r){return this.setLimit("min",e,!0,I.toString(r))}gt(e,r){return this.setLimit("min",e,!1,I.toString(r))}lte(e,r){return this.setLimit("max",e,!0,I.toString(r))}lt(e,r){return this.setLimit("max",e,!1,I.toString(r))}setLimit(e,r,s,i){return new t({...this._def,checks:[...this._def.checks,{kind:e,value:r,inclusive:s,message:I.toString(i)}]})}_addCheck(e){return new t({...this._def,checks:[...this._def.checks,e]})}positive(e){return this._addCheck({kind:"min",value:BigInt(0),inclusive:!1,message:I.toString(e)})}negative(e){return this._addCheck({kind:"max",value:BigInt(0),inclusive:!1,message:I.toString(e)})}nonpositive(e){return this._addCheck({kind:"max",value:BigInt(0),inclusive:!0,message:I.toString(e)})}nonnegative(e){return this._addCheck({kind:"min",value:BigInt(0),inclusive:!0,message:I.toString(e)})}multipleOf(e,r){return this._addCheck({kind:"multipleOf",value:e,message:I.toString(r)})}get minValue(){let e=null;for(let r of this._def.checks)r.kind==="min"&&(e===null||r.value>e)&&(e=r.value);return e}get maxValue(){let e=null;for(let r of this._def.checks)r.kind==="max"&&(e===null||r.value<e)&&(e=r.value);return e}};tt.create=t=>new tt({checks:[],typeName:P.ZodBigInt,coerce:t?.coerce??!1,...M(t)});var rt=class extends V{_parse(e){if(this._def.coerce&&(e.data=!!e.data),this._getType(e)!==E.boolean){let s=this._getOrReturnCtx(e);return T(s,{code:$.invalid_type,expected:E.boolean,received:s.parsedType}),j}return ae(e.data)}};rt.create=t=>new rt({typeName:P.ZodBoolean,coerce:t?.coerce||!1,...M(t)});var st=class t extends V{_parse(e){if(this._def.coerce&&(e.data=new Date(e.data)),this._getType(e)!==E.date){let a=this._getOrReturnCtx(e);return T(a,{code:$.invalid_type,expected:E.date,received:a.parsedType}),j}if(Number.isNaN(e.data.getTime())){let a=this._getOrReturnCtx(e);return T(a,{code:$.invalid_date}),j}let s=new re,i;for(let a of this._def.checks)a.kind==="min"?e.data.getTime()<a.value&&(i=this._getOrReturnCtx(e,i),T(i,{code:$.too_small,message:a.message,inclusive:!0,exact:!1,minimum:a.value,type:"date"}),s.dirty()):a.kind==="max"?e.data.getTime()>a.value&&(i=this._getOrReturnCtx(e,i),T(i,{code:$.too_big,message:a.message,inclusive:!0,exact:!1,maximum:a.value,type:"date"}),s.dirty()):H.assertNever(a);return{status:s.value,value:new Date(e.data.getTime())}}_addCheck(e){return new t({...this._def,checks:[...this._def.checks,e]})}min(e,r){return this._addCheck({kind:"min",value:e.getTime(),message:I.toString(r)})}max(e,r){return this._addCheck({kind:"max",value:e.getTime(),message:I.toString(r)})}get minDate(){let e=null;for(let r of this._def.checks)r.kind==="min"&&(e===null||r.value>e)&&(e=r.value);return e!=null?new Date(e):null}get maxDate(){let e=null;for(let r of this._def.checks)r.kind==="max"&&(e===null||r.value<e)&&(e=r.value);return e!=null?new Date(e):null}};st.create=t=>new st({checks:[],coerce:t?.coerce||!1,typeName:P.ZodDate,...M(t)});var Et=class extends V{_parse(e){if(this._getType(e)!==E.symbol){let s=this._getOrReturnCtx(e);return T(s,{code:$.invalid_type,expected:E.symbol,received:s.parsedType}),j}return ae(e.data)}};Et.create=t=>new Et({typeName:P.ZodSymbol,...M(t)});var it=class extends V{_parse(e){if(this._getType(e)!==E.undefined){let s=this._getOrReturnCtx(e);return T(s,{code:$.invalid_type,expected:E.undefined,received:s.parsedType}),j}return ae(e.data)}};it.create=t=>new it({typeName:P.ZodUndefined,...M(t)});var at=class extends V{_parse(e){if(this._getType(e)!==E.null){let s=this._getOrReturnCtx(e);return T(s,{code:$.invalid_type,expected:E.null,received:s.parsedType}),j}return ae(e.data)}};at.create=t=>new at({typeName:P.ZodNull,...M(t)});var Ze=class extends V{constructor(){super(...arguments),this._any=!0}_parse(e){return ae(e.data)}};Ze.create=t=>new Ze({typeName:P.ZodAny,...M(t)});var Oe=class extends V{constructor(){super(...arguments),this._unknown=!0}_parse(e){return ae(e.data)}};Oe.create=t=>new Oe({typeName:P.ZodUnknown,...M(t)});var _e=class extends V{_parse(e){let r=this._getOrReturnCtx(e);return T(r,{code:$.invalid_type,expected:E.never,received:r.parsedType}),j}};_e.create=t=>new _e({typeName:P.ZodNever,...M(t)});var At=class extends V{_parse(e){if(this._getType(e)!==E.undefined){let s=this._getOrReturnCtx(e);return T(s,{code:$.invalid_type,expected:E.void,received:s.parsedType}),j}return ae(e.data)}};At.create=t=>new At({typeName:P.ZodVoid,...M(t)});var je=class t extends V{_parse(e){let{ctx:r,status:s}=this._processInputParams(e),i=this._def;if(r.parsedType!==E.array)return T(r,{code:$.invalid_type,expected:E.array,received:r.parsedType}),j;if(i.exactLength!==null){let n=r.data.length>i.exactLength.value,o=r.data.length<i.exactLength.value;(n||o)&&(T(r,{code:n?$.too_big:$.too_small,minimum:o?i.exactLength.value:void 0,maximum:n?i.exactLength.value:void 0,type:"array",inclusive:!0,exact:!0,message:i.exactLength.message}),s.dirty())}if(i.minLength!==null&&r.data.length<i.minLength.value&&(T(r,{code:$.too_small,minimum:i.minLength.value,type:"array",inclusive:!0,exact:!1,message:i.minLength.message}),s.dirty()),i.maxLength!==null&&r.data.length>i.maxLength.value&&(T(r,{code:$.too_big,maximum:i.maxLength.value,type:"array",inclusive:!0,exact:!1,message:i.maxLength.message}),s.dirty()),r.common.async)return Promise.all([...r.data].map((n,o)=>i.type._parseAsync(new fe(r,n,r.path,o)))).then(n=>re.mergeArray(s,n));let a=[...r.data].map((n,o)=>i.type._parseSync(new fe(r,n,r.path,o)));return re.mergeArray(s,a)}get element(){return this._def.type}min(e,r){return new t({...this._def,minLength:{value:e,message:I.toString(r)}})}max(e,r){return new t({...this._def,maxLength:{value:e,message:I.toString(r)}})}length(e,r){return new t({...this._def,exactLength:{value:e,message:I.toString(r)}})}nonempty(e){return this.min(1,e)}};je.create=(t,e)=>new je({type:t,minLength:null,maxLength:null,exactLength:null,typeName:P.ZodArray,...M(e)});function Tt(t){if(t instanceof ce){let e={};for(let r in t.shape){let s=t.shape[r];e[r]=pe.create(Tt(s))}return new ce({...t._def,shape:()=>e})}else return t instanceof je?new je({...t._def,type:Tt(t.element)}):t instanceof pe?pe.create(Tt(t.unwrap())):t instanceof Se?Se.create(Tt(t.unwrap())):t instanceof $e?$e.create(t.items.map(e=>Tt(e))):t}var ce=class t extends V{constructor(){super(...arguments),this._cached=null,this.nonstrict=this.passthrough,this.augment=this.extend}_getCached(){if(this._cached!==null)return this._cached;let e=this._def.shape(),r=H.objectKeys(e);return this._cached={shape:e,keys:r},this._cached}_parse(e){if(this._getType(e)!==E.object){let u=this._getOrReturnCtx(e);return T(u,{code:$.invalid_type,expected:E.object,received:u.parsedType}),j}let{status:s,ctx:i}=this._processInputParams(e),{shape:a,keys:n}=this._getCached(),o=[];if(!(this._def.catchall instanceof _e&&this._def.unknownKeys==="strip"))for(let u in i.data)n.includes(u)||o.push(u);let d=[];for(let u of n){let c=a[u],l=i.data[u];d.push({key:{status:"valid",value:u},value:c._parse(new fe(i,l,i.path,u)),alwaysSet:u in i.data})}if(this._def.catchall instanceof _e){let u=this._def.unknownKeys;if(u==="passthrough")for(let c of o)d.push({key:{status:"valid",value:c},value:{status:"valid",value:i.data[c]}});else if(u==="strict")o.length>0&&(T(i,{code:$.unrecognized_keys,keys:o}),s.dirty());else if(u!=="strip")throw new Error("Internal ZodObject error: invalid unknownKeys value.")}else{let u=this._def.catchall;for(let c of o){let l=i.data[c];d.push({key:{status:"valid",value:c},value:u._parse(new fe(i,l,i.path,c)),alwaysSet:c in i.data})}}return i.common.async?Promise.resolve().then(async()=>{let u=[];for(let c of d){let l=await c.key,p=await c.value;u.push({key:l,value:p,alwaysSet:c.alwaysSet})}return u}).then(u=>re.mergeObjectSync(s,u)):re.mergeObjectSync(s,d)}get shape(){return this._def.shape()}strict(e){return I.errToObj,new t({...this._def,unknownKeys:"strict",...e!==void 0?{errorMap:(r,s)=>{let i=this._def.errorMap?.(r,s).message??s.defaultError;return r.code==="unrecognized_keys"?{message:I.errToObj(e).message??i}:{message:i}}}:{}})}strip(){return new t({...this._def,unknownKeys:"strip"})}passthrough(){return new t({...this._def,unknownKeys:"passthrough"})}extend(e){return new t({...this._def,shape:()=>({...this._def.shape(),...e})})}merge(e){return new t({unknownKeys:e._def.unknownKeys,catchall:e._def.catchall,shape:()=>({...this._def.shape(),...e._def.shape()}),typeName:P.ZodObject})}setKey(e,r){return this.augment({[e]:r})}catchall(e){return new t({...this._def,catchall:e})}pick(e){let r={};for(let s of H.objectKeys(e))e[s]&&this.shape[s]&&(r[s]=this.shape[s]);return new t({...this._def,shape:()=>r})}omit(e){let r={};for(let s of H.objectKeys(this.shape))e[s]||(r[s]=this.shape[s]);return new t({...this._def,shape:()=>r})}deepPartial(){return Tt(this)}partial(e){let r={};for(let s of H.objectKeys(this.shape)){let i=this.shape[s];e&&!e[s]?r[s]=i:r[s]=i.optional()}return new t({...this._def,shape:()=>r})}required(e){let r={};for(let s of H.objectKeys(this.shape))if(e&&!e[s])r[s]=this.shape[s];else{let a=this.shape[s];for(;a instanceof pe;)a=a._def.innerType;r[s]=a}return new t({...this._def,shape:()=>r})}keyof(){return Wi(H.objectKeys(this.shape))}};ce.create=(t,e)=>new ce({shape:()=>t,unknownKeys:"strip",catchall:_e.create(),typeName:P.ZodObject,...M(e)});ce.strictCreate=(t,e)=>new ce({shape:()=>t,unknownKeys:"strict",catchall:_e.create(),typeName:P.ZodObject,...M(e)});ce.lazycreate=(t,e)=>new ce({shape:t,unknownKeys:"strip",catchall:_e.create(),typeName:P.ZodObject,...M(e)});var nt=class extends V{_parse(e){let{ctx:r}=this._processInputParams(e),s=this._def.options;function i(a){for(let o of a)if(o.result.status==="valid")return o.result;for(let o of a)if(o.result.status==="dirty")return r.common.issues.push(...o.ctx.common.issues),o.result;let n=a.map(o=>new le(o.ctx.common.issues));return T(r,{code:$.invalid_union,unionErrors:n}),j}if(r.common.async)return Promise.all(s.map(async a=>{let n={...r,common:{...r.common,issues:[]},parent:null};return{result:await a._parseAsync({data:r.data,path:r.path,parent:n}),ctx:n}})).then(i);{let a,n=[];for(let d of s){let u={...r,common:{...r.common,issues:[]},parent:null},c=d._parseSync({data:r.data,path:r.path,parent:u});if(c.status==="valid")return c;c.status==="dirty"&&!a&&(a={result:c,ctx:u}),u.common.issues.length&&n.push(u.common.issues)}if(a)return r.common.issues.push(...a.ctx.common.issues),a.result;let o=n.map(d=>new le(d));return T(r,{code:$.invalid_union,unionErrors:o}),j}}get options(){return this._def.options}};nt.create=(t,e)=>new nt({options:t,typeName:P.ZodUnion,...M(e)});var Re=t=>t instanceof lt?Re(t.schema):t instanceof me?Re(t.innerType()):t instanceof ct?[t.value]:t instanceof ut?t.options:t instanceof dt?H.objectValues(t.enum):t instanceof ht?Re(t._def.innerType):t instanceof it?[void 0]:t instanceof at?[null]:t instanceof pe?[void 0,...Re(t.unwrap())]:t instanceof Se?[null,...Re(t.unwrap())]:t instanceof Wt||t instanceof ft?Re(t.unwrap()):t instanceof pt?Re(t._def.innerType):[],Rr=class t extends V{_parse(e){let{ctx:r}=this._processInputParams(e);if(r.parsedType!==E.object)return T(r,{code:$.invalid_type,expected:E.object,received:r.parsedType}),j;let s=this.discriminator,i=r.data[s],a=this.optionsMap.get(i);return a?r.common.async?a._parseAsync({data:r.data,path:r.path,parent:r}):a._parseSync({data:r.data,path:r.path,parent:r}):(T(r,{code:$.invalid_union_discriminator,options:Array.from(this.optionsMap.keys()),path:[s]}),j)}get discriminator(){return this._def.discriminator}get options(){return this._def.options}get optionsMap(){return this._def.optionsMap}static create(e,r,s){let i=new Map;for(let a of r){let n=Re(a.shape[e]);if(!n.length)throw new Error(`A discriminator value for key \`${e}\` could not be extracted from all schema options`);for(let o of n){if(i.has(o))throw new Error(`Discriminator property ${String(e)} has duplicate value ${String(o)}`);i.set(o,a)}}return new t({typeName:P.ZodDiscriminatedUnion,discriminator:e,options:r,optionsMap:i,...M(s)})}};function zs(t,e){let r=we(t),s=we(e);if(t===e)return{valid:!0,data:t};if(r===E.object&&s===E.object){let i=H.objectKeys(e),a=H.objectKeys(t).filter(o=>i.indexOf(o)!==-1),n={...t,...e};for(let o of a){let d=zs(t[o],e[o]);if(!d.valid)return{valid:!1};n[o]=d.data}return{valid:!0,data:n}}else if(r===E.array&&s===E.array){if(t.length!==e.length)return{valid:!1};let i=[];for(let a=0;a<t.length;a++){let n=t[a],o=e[a],d=zs(n,o);if(!d.valid)return{valid:!1};i.push(d.data)}return{valid:!0,data:i}}else return r===E.date&&s===E.date&&+t==+e?{valid:!0,data:t}:{valid:!1}}var ot=class extends V{_parse(e){let{status:r,ctx:s}=this._processInputParams(e),i=(a,n)=>{if(Ar(a)||Ar(n))return j;let o=zs(a.value,n.value);return o.valid?((Ir(a)||Ir(n))&&r.dirty(),{status:r.value,value:o.data}):(T(s,{code:$.invalid_intersection_types}),j)};return s.common.async?Promise.all([this._def.left._parseAsync({data:s.data,path:s.path,parent:s}),this._def.right._parseAsync({data:s.data,path:s.path,parent:s})]).then(([a,n])=>i(a,n)):i(this._def.left._parseSync({data:s.data,path:s.path,parent:s}),this._def.right._parseSync({data:s.data,path:s.path,parent:s}))}};ot.create=(t,e,r)=>new ot({left:t,right:e,typeName:P.ZodIntersection,...M(r)});var $e=class t extends V{_parse(e){let{status:r,ctx:s}=this._processInputParams(e);if(s.parsedType!==E.array)return T(s,{code:$.invalid_type,expected:E.array,received:s.parsedType}),j;if(s.data.length<this._def.items.length)return T(s,{code:$.too_small,minimum:this._def.items.length,inclusive:!0,exact:!1,type:"array"}),j;!this._def.rest&&s.data.length>this._def.items.length&&(T(s,{code:$.too_big,maximum:this._def.items.length,inclusive:!0,exact:!1,type:"array"}),r.dirty());let a=[...s.data].map((n,o)=>{let d=this._def.items[o]||this._def.rest;return d?d._parse(new fe(s,n,s.path,o)):null}).filter(n=>!!n);return s.common.async?Promise.all(a).then(n=>re.mergeArray(r,n)):re.mergeArray(r,a)}get items(){return this._def.items}rest(e){return new t({...this._def,rest:e})}};$e.create=(t,e)=>{if(!Array.isArray(t))throw new Error("You must pass an array of schemas to z.tuple([ ... ])");return new $e({items:t,typeName:P.ZodTuple,rest:null,...M(e)})};var Or=class t extends V{get keySchema(){return this._def.keyType}get valueSchema(){return this._def.valueType}_parse(e){let{status:r,ctx:s}=this._processInputParams(e);if(s.parsedType!==E.object)return T(s,{code:$.invalid_type,expected:E.object,received:s.parsedType}),j;let i=[],a=this._def.keyType,n=this._def.valueType;for(let o in s.data)i.push({key:a._parse(new fe(s,o,s.path,o)),value:n._parse(new fe(s,s.data[o],s.path,o)),alwaysSet:o in s.data});return s.common.async?re.mergeObjectAsync(r,i):re.mergeObjectSync(r,i)}get element(){return this._def.valueType}static create(e,r,s){return r instanceof V?new t({keyType:e,valueType:r,typeName:P.ZodRecord,...M(s)}):new t({keyType:We.create(),valueType:e,typeName:P.ZodRecord,...M(r)})}},It=class extends V{get keySchema(){return this._def.keyType}get valueSchema(){return this._def.valueType}_parse(e){let{status:r,ctx:s}=this._processInputParams(e);if(s.parsedType!==E.map)return T(s,{code:$.invalid_type,expected:E.map,received:s.parsedType}),j;let i=this._def.keyType,a=this._def.valueType,n=[...s.data.entries()].map(([o,d],u)=>({key:i._parse(new fe(s,o,s.path,[u,"key"])),value:a._parse(new fe(s,d,s.path,[u,"value"]))}));if(s.common.async){let o=new Map;return Promise.resolve().then(async()=>{for(let d of n){let u=await d.key,c=await d.value;if(u.status==="aborted"||c.status==="aborted")return j;(u.status==="dirty"||c.status==="dirty")&&r.dirty(),o.set(u.value,c.value)}return{status:r.value,value:o}})}else{let o=new Map;for(let d of n){let u=d.key,c=d.value;if(u.status==="aborted"||c.status==="aborted")return j;(u.status==="dirty"||c.status==="dirty")&&r.dirty(),o.set(u.value,c.value)}return{status:r.value,value:o}}}};It.create=(t,e,r)=>new It({valueType:e,keyType:t,typeName:P.ZodMap,...M(r)});var Rt=class t extends V{_parse(e){let{status:r,ctx:s}=this._processInputParams(e);if(s.parsedType!==E.set)return T(s,{code:$.invalid_type,expected:E.set,received:s.parsedType}),j;let i=this._def;i.minSize!==null&&s.data.size<i.minSize.value&&(T(s,{code:$.too_small,minimum:i.minSize.value,type:"set",inclusive:!0,exact:!1,message:i.minSize.message}),r.dirty()),i.maxSize!==null&&s.data.size>i.maxSize.value&&(T(s,{code:$.too_big,maximum:i.maxSize.value,type:"set",inclusive:!0,exact:!1,message:i.maxSize.message}),r.dirty());let a=this._def.valueType;function n(d){let u=new Set;for(let c of d){if(c.status==="aborted")return j;c.status==="dirty"&&r.dirty(),u.add(c.value)}return{status:r.value,value:u}}let o=[...s.data.values()].map((d,u)=>a._parse(new fe(s,d,s.path,u)));return s.common.async?Promise.all(o).then(d=>n(d)):n(o)}min(e,r){return new t({...this._def,minSize:{value:e,message:I.toString(r)}})}max(e,r){return new t({...this._def,maxSize:{value:e,message:I.toString(r)}})}size(e,r){return this.min(e,r).max(e,r)}nonempty(e){return this.min(1,e)}};Rt.create=(t,e)=>new Rt({valueType:t,minSize:null,maxSize:null,typeName:P.ZodSet,...M(e)});var jr=class t extends V{constructor(){super(...arguments),this.validate=this.implement}_parse(e){let{ctx:r}=this._processInputParams(e);if(r.parsedType!==E.function)return T(r,{code:$.invalid_type,expected:E.function,received:r.parsedType}),j;function s(o,d){return qt({data:o,path:r.path,errorMaps:[r.common.contextualErrorMap,r.schemaErrorMap,Ct(),Ie].filter(u=>!!u),issueData:{code:$.invalid_arguments,argumentsError:d}})}function i(o,d){return qt({data:o,path:r.path,errorMaps:[r.common.contextualErrorMap,r.schemaErrorMap,Ct(),Ie].filter(u=>!!u),issueData:{code:$.invalid_return_type,returnTypeError:d}})}let a={errorMap:r.common.contextualErrorMap},n=r.data;if(this._def.returns instanceof Ge){let o=this;return ae(async function(...d){let u=new le([]),c=await o._def.args.parseAsync(d,a).catch(h=>{throw u.addIssue(s(d,h)),u}),l=await Reflect.apply(n,this,c);return await o._def.returns._def.type.parseAsync(l,a).catch(h=>{throw u.addIssue(i(l,h)),u})})}else{let o=this;return ae(function(...d){let u=o._def.args.safeParse(d,a);if(!u.success)throw new le([s(d,u.error)]);let c=Reflect.apply(n,this,u.data),l=o._def.returns.safeParse(c,a);if(!l.success)throw new le([i(c,l.error)]);return l.data})}}parameters(){return this._def.args}returnType(){return this._def.returns}args(...e){return new t({...this._def,args:$e.create(e).rest(Oe.create())})}returns(e){return new t({...this._def,returns:e})}implement(e){return this.parse(e)}strictImplement(e){return this.parse(e)}static create(e,r,s){return new t({args:e||$e.create([]).rest(Oe.create()),returns:r||Oe.create(),typeName:P.ZodFunction,...M(s)})}},lt=class extends V{get schema(){return this._def.getter()}_parse(e){let{ctx:r}=this._processInputParams(e);return this._def.getter()._parse({data:r.data,path:r.path,parent:r})}};lt.create=(t,e)=>new lt({getter:t,typeName:P.ZodLazy,...M(e)});var ct=class extends V{_parse(e){if(e.data!==this._def.value){let r=this._getOrReturnCtx(e);return T(r,{received:r.data,code:$.invalid_literal,expected:this._def.value}),j}return{status:"valid",value:e.data}}get value(){return this._def.value}};ct.create=(t,e)=>new ct({value:t,typeName:P.ZodLiteral,...M(e)});function Wi(t,e){return new ut({values:t,typeName:P.ZodEnum,...M(e)})}var ut=class t extends V{_parse(e){if(typeof e.data!="string"){let r=this._getOrReturnCtx(e),s=this._def.values;return T(r,{expected:H.joinValues(s),received:r.parsedType,code:$.invalid_type}),j}if(this._cache||(this._cache=new Set(this._def.values)),!this._cache.has(e.data)){let r=this._getOrReturnCtx(e),s=this._def.values;return T(r,{received:r.data,code:$.invalid_enum_value,options:s}),j}return ae(e.data)}get options(){return this._def.values}get enum(){let e={};for(let r of this._def.values)e[r]=r;return e}get Values(){let e={};for(let r of this._def.values)e[r]=r;return e}get Enum(){let e={};for(let r of this._def.values)e[r]=r;return e}extract(e,r=this._def){return t.create(e,{...this._def,...r})}exclude(e,r=this._def){return t.create(this.options.filter(s=>!e.includes(s)),{...this._def,...r})}};ut.create=Wi;var dt=class extends V{_parse(e){let r=H.getValidEnumValues(this._def.values),s=this._getOrReturnCtx(e);if(s.parsedType!==E.string&&s.parsedType!==E.number){let i=H.objectValues(r);return T(s,{expected:H.joinValues(i),received:s.parsedType,code:$.invalid_type}),j}if(this._cache||(this._cache=new Set(H.getValidEnumValues(this._def.values))),!this._cache.has(e.data)){let i=H.objectValues(r);return T(s,{received:s.data,code:$.invalid_enum_value,options:i}),j}return ae(e.data)}get enum(){return this._def.values}};dt.create=(t,e)=>new dt({values:t,typeName:P.ZodNativeEnum,...M(e)});var Ge=class extends V{unwrap(){return this._def.type}_parse(e){let{ctx:r}=this._processInputParams(e);if(r.parsedType!==E.promise&&r.common.async===!1)return T(r,{code:$.invalid_type,expected:E.promise,received:r.parsedType}),j;let s=r.parsedType===E.promise?r.data:Promise.resolve(r.data);return ae(s.then(i=>this._def.type.parseAsync(i,{path:r.path,errorMap:r.common.contextualErrorMap})))}};Ge.create=(t,e)=>new Ge({type:t,typeName:P.ZodPromise,...M(e)});var me=class extends V{innerType(){return this._def.schema}sourceType(){return this._def.schema._def.typeName===P.ZodEffects?this._def.schema.sourceType():this._def.schema}_parse(e){let{status:r,ctx:s}=this._processInputParams(e),i=this._def.effect||null,a={addIssue:n=>{T(s,n),n.fatal?r.abort():r.dirty()},get path(){return s.path}};if(a.addIssue=a.addIssue.bind(a),i.type==="preprocess"){let n=i.transform(s.data,a);if(s.common.async)return Promise.resolve(n).then(async o=>{if(r.value==="aborted")return j;let d=await this._def.schema._parseAsync({data:o,path:s.path,parent:s});return d.status==="aborted"?j:d.status==="dirty"?Qe(d.value):r.value==="dirty"?Qe(d.value):d});{if(r.value==="aborted")return j;let o=this._def.schema._parseSync({data:n,path:s.path,parent:s});return o.status==="aborted"?j:o.status==="dirty"?Qe(o.value):r.value==="dirty"?Qe(o.value):o}}if(i.type==="refinement"){let n=o=>{let d=i.refinement(o,a);if(s.common.async)return Promise.resolve(d);if(d instanceof Promise)throw new Error("Async refinement encountered during synchronous parse operation. Use .parseAsync instead.");return o};if(s.common.async===!1){let o=this._def.schema._parseSync({data:s.data,path:s.path,parent:s});return o.status==="aborted"?j:(o.status==="dirty"&&r.dirty(),n(o.value),{status:r.value,value:o.value})}else return this._def.schema._parseAsync({data:s.data,path:s.path,parent:s}).then(o=>o.status==="aborted"?j:(o.status==="dirty"&&r.dirty(),n(o.value).then(()=>({status:r.value,value:o.value}))))}if(i.type==="transform")if(s.common.async===!1){let n=this._def.schema._parseSync({data:s.data,path:s.path,parent:s});if(!qe(n))return j;let o=i.transform(n.value,a);if(o instanceof Promise)throw new Error("Asynchronous transform encountered during synchronous parse operation. Use .parseAsync instead.");return{status:r.value,value:o}}else return this._def.schema._parseAsync({data:s.data,path:s.path,parent:s}).then(n=>qe(n)?Promise.resolve(i.transform(n.value,a)).then(o=>({status:r.value,value:o})):j);H.assertNever(i)}};me.create=(t,e,r)=>new me({schema:t,typeName:P.ZodEffects,effect:e,...M(r)});me.createWithPreprocess=(t,e,r)=>new me({schema:e,effect:{type:"preprocess",transform:t},typeName:P.ZodEffects,...M(r)});var pe=class extends V{_parse(e){return this._getType(e)===E.undefined?ae(void 0):this._def.innerType._parse(e)}unwrap(){return this._def.innerType}};pe.create=(t,e)=>new pe({innerType:t,typeName:P.ZodOptional,...M(e)});var Se=class extends V{_parse(e){return this._getType(e)===E.null?ae(null):this._def.innerType._parse(e)}unwrap(){return this._def.innerType}};Se.create=(t,e)=>new Se({innerType:t,typeName:P.ZodNullable,...M(e)});var ht=class extends V{_parse(e){let{ctx:r}=this._processInputParams(e),s=r.data;return r.parsedType===E.undefined&&(s=this._def.defaultValue()),this._def.innerType._parse({data:s,path:r.path,parent:r})}removeDefault(){return this._def.innerType}};ht.create=(t,e)=>new ht({innerType:t,typeName:P.ZodDefault,defaultValue:typeof e.default=="function"?e.default:()=>e.default,...M(e)});var pt=class extends V{_parse(e){let{ctx:r}=this._processInputParams(e),s={...r,common:{...r.common,issues:[]}},i=this._def.innerType._parse({data:s.data,path:s.path,parent:{...s}});return kt(i)?i.then(a=>({status:"valid",value:a.status==="valid"?a.value:this._def.catchValue({get error(){return new le(s.common.issues)},input:s.data})})):{status:"valid",value:i.status==="valid"?i.value:this._def.catchValue({get error(){return new le(s.common.issues)},input:s.data})}}removeCatch(){return this._def.innerType}};pt.create=(t,e)=>new pt({innerType:t,typeName:P.ZodCatch,catchValue:typeof e.catch=="function"?e.catch:()=>e.catch,...M(e)});var Ot=class extends V{_parse(e){if(this._getType(e)!==E.nan){let s=this._getOrReturnCtx(e);return T(s,{code:$.invalid_type,expected:E.nan,received:s.parsedType}),j}return{status:"valid",value:e.data}}};Ot.create=t=>new Ot({typeName:P.ZodNaN,...M(t)});var no=Symbol("zod_brand"),Wt=class extends V{_parse(e){let{ctx:r}=this._processInputParams(e),s=r.data;return this._def.type._parse({data:s,path:r.path,parent:r})}unwrap(){return this._def.type}},Zt=class t extends V{_parse(e){let{status:r,ctx:s}=this._processInputParams(e);if(s.common.async)return(async()=>{let a=await this._def.in._parseAsync({data:s.data,path:s.path,parent:s});return a.status==="aborted"?j:a.status==="dirty"?(r.dirty(),Qe(a.value)):this._def.out._parseAsync({data:a.value,path:s.path,parent:s})})();{let i=this._def.in._parseSync({data:s.data,path:s.path,parent:s});return i.status==="aborted"?j:i.status==="dirty"?(r.dirty(),{status:"dirty",value:i.value}):this._def.out._parseSync({data:i.value,path:s.path,parent:s})}}static create(e,r){return new t({in:e,out:r,typeName:P.ZodPipeline})}},ft=class extends V{_parse(e){let r=this._def.innerType._parse(e),s=i=>(qe(i)&&(i.value=Object.freeze(i.value)),i);return kt(r)?r.then(i=>s(i)):s(r)}unwrap(){return this._def.innerType}};ft.create=(t,e)=>new ft({innerType:t,typeName:P.ZodReadonly,...M(e)});function Fi(t,e){let r=typeof t=="function"?t(e):typeof t=="string"?{message:t}:t;return typeof r=="string"?{message:r}:r}function Zi(t,e={},r){return t?Ze.create().superRefine((s,i)=>{let a=t(s);if(a instanceof Promise)return a.then(n=>{if(!n){let o=Fi(e,s),d=o.fatal??r??!0;i.addIssue({code:"custom",...o,fatal:d})}});if(!a){let n=Fi(e,s),o=n.fatal??r??!0;i.addIssue({code:"custom",...n,fatal:o})}}):Ze.create()}var oo={object:ce.lazycreate},P;(function(t){t.ZodString="ZodString",t.ZodNumber="ZodNumber",t.ZodNaN="ZodNaN",t.ZodBigInt="ZodBigInt",t.ZodBoolean="ZodBoolean",t.ZodDate="ZodDate",t.ZodSymbol="ZodSymbol",t.ZodUndefined="ZodUndefined",t.ZodNull="ZodNull",t.ZodAny="ZodAny",t.ZodUnknown="ZodUnknown",t.ZodNever="ZodNever",t.ZodVoid="ZodVoid",t.ZodArray="ZodArray",t.ZodObject="ZodObject",t.ZodUnion="ZodUnion",t.ZodDiscriminatedUnion="ZodDiscriminatedUnion",t.ZodIntersection="ZodIntersection",t.ZodTuple="ZodTuple",t.ZodRecord="ZodRecord",t.ZodMap="ZodMap",t.ZodSet="ZodSet",t.ZodFunction="ZodFunction",t.ZodLazy="ZodLazy",t.ZodLiteral="ZodLiteral",t.ZodEnum="ZodEnum",t.ZodEffects="ZodEffects",t.ZodNativeEnum="ZodNativeEnum",t.ZodOptional="ZodOptional",t.ZodNullable="ZodNullable",t.ZodDefault="ZodDefault",t.ZodCatch="ZodCatch",t.ZodPromise="ZodPromise",t.ZodBranded="ZodBranded",t.ZodPipeline="ZodPipeline",t.ZodReadonly="ZodReadonly"})(P||(P={}));var lo=(t,e={message:`Input not instance of ${t.name}`})=>Zi(r=>r instanceof t,e),Gi=We.create,Xi=et.create,co=Ot.create,uo=tt.create,Ki=rt.create,ho=st.create,po=Et.create,fo=it.create,mo=at.create,go=Ze.create,yo=Oe.create,vo=_e.create,_o=At.create,bo=je.create,xo=ce.create,wo=ce.strictCreate,$o=nt.create,So=Rr.create,Co=ot.create,ko=$e.create,To=Or.create,Eo=It.create,Ao=Rt.create,Io=jr.create,Ro=lt.create,Oo=ct.create,jo=ut.create,Po=dt.create,Do=Ge.create,No=me.create,Mo=pe.create,zo=Se.create,Vo=me.createWithPreprocess,Uo=Zt.create,Lo=()=>Gi().optional(),Fo=()=>Xi().optional(),Bo=()=>Ki().optional(),Ho={string:(t=>We.create({...t,coerce:!0})),number:(t=>et.create({...t,coerce:!0})),boolean:(t=>rt.create({...t,coerce:!0})),bigint:(t=>tt.create({...t,coerce:!0})),date:(t=>st.create({...t,coerce:!0}))};var qo=j;var Ce=(t,e)=>{let r=Object.keys(t).filter(s=>t[s]!==void 0);r.length!==1&&e.addIssue({code:x.ZodIssueCode.custom,message:`Must define exactly one property, found ${r.length} (${r.join(", ")}).`})},ge=x.object({path:x.string().optional(),literalString:x.string().optional(),literal:x.string().optional()}).strict().superRefine(Ce),Yi=x.lazy(()=>x.object({key:x.string(),valueString:x.string().optional(),valueNumber:x.number().optional(),valueBoolean:x.boolean().optional(),valueMap:x.array(Yi).optional()}).strict().superRefine((t,e)=>{let r=0;t.valueString!==void 0&&r++,t.valueNumber!==void 0&&r++,t.valueBoolean!==void 0&&r++,t.valueMap!==void 0&&r++,r!==1&&e.addIssue({code:x.ZodIssueCode.custom,message:`Value map item must have exactly one value property (valueString, valueNumber, valueBoolean, valueMap), found ${r}.`})}));function Wo(t={}){let e=t.maxDepth??5;return Yi.superRefine((r,s)=>{let i=(a,n)=>{if(n>e){s.addIssue({code:x.ZodIssueCode.custom,message:`valueMap recursion exceeded maximum depth of ${e}.`});return}if(a.valueMap&&Array.isArray(a.valueMap))for(let o of a.valueMap)i(o,n+1)};i(r,1)})}var Ji=Wo(),yu=x.object({path:x.string().optional(),literalNumber:x.number().optional(),literal:x.number().optional()}).strict().superRefine(Ce),vu=x.object({path:x.string().optional(),literalBoolean:x.boolean().optional(),literal:x.boolean().optional()}).strict().superRefine(Ce),Zo=x.object({name:x.string().describe("A unique name identifying the action (e.g., 'submitForm')."),context:x.array(x.object({key:x.string(),value:x.object({path:x.string().describe("A data binding reference to a location in the data model (e.g., '/user/name').").optional(),literalString:x.string().describe("A fixed, hardcoded string value.").optional(),literalNumber:x.number().optional(),literalBoolean:x.boolean().optional()}).describe("The dynamic value. Define EXACTLY ONE of the nested properties.").strict().superRefine(Ce)})).describe("A key-value map of data bindings to be resolved when the action is triggered.").optional()}),_u=x.object({text:ge,usageHint:x.enum(["h1","h2","h3","h4","h5","caption","body"]).optional()}),bu=x.object({url:ge,usageHint:x.enum(["icon","avatar","smallFeature","mediumFeature","largeFeature","header"]).optional(),fit:x.enum(["contain","cover","fill","none","scale-down"]).optional(),altText:ge.optional()}),xu=x.object({name:ge}),wu=x.object({url:ge}),$u=x.object({url:ge,description:ge.optional().describe("A label, title, or placeholder text.")}),Su=x.object({tabItems:x.array(x.object({title:x.object({path:x.string().describe("A data binding reference to a location in the data model (e.g., '/user/name').").optional(),literalString:x.string().describe("A fixed, hardcoded string value.").optional()}),child:x.string().describe("A reference to a component instance by its unique ID.")}).strict().superRefine((t,e)=>{t.title||e.addIssue({code:x.ZodIssueCode.custom,message:"Tab item is missing 'title'."}),t.child||e.addIssue({code:x.ZodIssueCode.custom,message:"Tab item is missing 'child'."}),t.title&&Ce(t.title,e)})).describe("A list of tabs, each with a title and a child component ID.")}),Cu=x.object({axis:x.enum(["horizontal","vertical"]).optional().describe("The orientation."),color:x.string().optional().describe("The color of the divider (e.g., hex code or semantic name)."),thickness:x.number().optional().describe("The thickness of the divider.")}),ku=x.object({entryPointChild:x.string().describe("The ID of the component (e.g., a button) that triggers the modal."),contentChild:x.string().describe("The ID of the component to display as the modal's content.")}),Tu=x.object({child:x.string().describe("The ID of the component to display as the button's content."),action:Zo.describe("Represents a user-initiated action."),primary:x.boolean().optional().describe("Indicates if this button should be styled as the primary action.")}),Eu=x.object({label:ge,value:x.object({path:x.string().describe("A data binding reference to a location in the data model (e.g., '/user/name').").optional(),literalBoolean:x.boolean().optional()}).strict().superRefine(Ce)}),Au=x.object({text:ge.optional(),label:ge.describe("A label, title, or placeholder text."),textFieldType:x.enum(["shortText","number","date","longText","obscured"]).optional(),validationRegexp:x.string().optional().describe("A regex string to validate the input.")}),Iu=x.object({value:ge,enableDate:x.boolean().optional(),enableTime:x.boolean().optional(),outputFormat:x.string().optional().describe("The string format for the output (e.g., 'YYYY-MM-DD').")}),Ru=x.object({selections:x.object({path:x.string().describe("A data binding reference to a location in the data model (e.g., '/user/name').").optional(),literalArray:x.array(x.string()).optional()}).strict().superRefine(Ce),options:x.array(x.object({label:x.object({path:x.string().describe("A data binding reference to a location in the data model (e.g., '/user/name').").optional(),literalString:x.string().describe("A fixed, hardcoded string value.").optional()}).strict().superRefine(Ce),value:x.string()})).optional(),maxAllowedSelections:x.number().optional(),type:x.enum(["checkbox","chips"]).optional(),filterable:x.boolean().optional()}),Ou=x.object({value:x.object({path:x.string().describe("A data binding reference to a location in the data model (e.g., '/user/name').").optional(),literalNumber:x.number().optional()}).strict().superRefine(Ce),minValue:x.number().optional(),maxValue:x.number().optional(),label:ge.optional()}),Go=x.object({componentId:x.string(),dataBinding:x.string()}),Vs=x.object({explicitList:x.array(x.string()).optional(),template:Go.describe("A template for generating a dynamic list of children from a data model list. `componentId` is the component to use as a template, and `dataBinding` is the path to the map of components in the data model. Values in the map will define the list of children.").optional()}).strict().superRefine(Ce),ju=x.object({children:Vs,distribution:x.enum(["start","center","end","spaceBetween","spaceAround","spaceEvenly"]).optional(),alignment:x.enum(["start","center","end","stretch"]).optional()}),Pu=x.object({children:Vs,distribution:x.enum(["start","center","end","spaceBetween","spaceAround","spaceEvenly"]).optional(),alignment:x.enum(["start","center","end","stretch"]).optional()}),Du=x.object({children:Vs,direction:x.enum(["vertical","horizontal"]).optional(),alignment:x.enum(["start","center","end","stretch"]).optional()}),Nu=x.object({child:x.string().describe("The ID of the component to be rendered inside the card.")});var Xo=Ji.describe("A single data entry. Exactly one 'value*' property should be provided alongside the key."),Ko=x.record(x.any()).refine(t=>Object.keys(t).length===1,"A wrapper object that MUST contain exactly one key, which is the name of the component type (e.g., 'Heading').");var Yo=x.object({id:x.string().describe("The unique identifier for this component."),weight:x.number().optional().describe("The relative weight of this component within a Row or Column. This corresponds to the CSS 'flex-grow' property. Note: this may ONLY be set when the component is a direct descendant of a Row or Column."),component:Ko.describe("A wrapper object that MUST contain exactly one key, which is the name of the component type (e.g., 'Heading'). The value is an object containing the properties for that specific component.")}).strict().describe("Represents a *single* component in a UI widget tree. This component could be one of many supported types."),Jo=x.object({surfaceId:x.string().describe("The unique identifier for the UI surface to be rendered."),catalogId:x.string().optional().describe("The identifier of the component catalog to use for this surface. If omitted, the client MUST default to the standard catalog for this A2UI version (https://a2ui.org/specification/v0_8/standard_catalog_definition.json)."),root:x.string().describe("The ID of the root component to render."),styles:x.object({font:x.string().optional().describe("The primary font for the UI."),primaryColor:x.string().regex(/^#[0-9a-fA-F]{6}$/).optional().describe("The primary UI color as a hexadecimal code (e.g., '#00BFFF').")}).strict().optional().describe("Styling information for the UI.")}).strict().describe("Signals the client to begin rendering a surface with a root component and specific styles."),Qo=x.object({surfaceId:x.string().describe("The unique identifier for the UI surface to be updated. If you are adding a new surface this *must* be a new, unique identified that has never been used for any existing surfaces shown."),components:x.array(Yo).min(1).describe("A list containing all UI components for the surface.")}).strict().superRefine((t,e)=>{let r=new Set;for(let i of t.components)i.id&&(r.has(i.id)&&e.addIssue({code:x.ZodIssueCode.custom,message:`Duplicate component ID found: ${i.id}`,path:["components"]}),r.add(i.id));let s=(i,a)=>{for(let n of i)n&&!r.has(n)&&e.addIssue({code:x.ZodIssueCode.custom,message:`Component '${a}' references non-existent component ID '${n}'.`,path:["components"]})};for(let i of t.components){if(!i.id||!i.component)continue;let a=Object.keys(i.component);if(a.length!==1)continue;let n=a[0],o=i.component[n];switch(n){case"Row":case"Column":case"List":if(o.children&&!Array.isArray(o.children)){let d=!!o.children.explicitList,u=!!o.children.template;(d&&u||!d&&!u)&&e.addIssue({code:x.ZodIssueCode.custom,message:`Component '${i.id}' must have either 'explicitList' or 'template' in children, but not both or neither.`}),d&&s(o.children.explicitList,i.id),u&&s([o.children.template?.componentId],i.id)}break;case"Card":o.child&&s([o.child],i.id);break;case"Tabs":o.tabItems&&Array.isArray(o.tabItems)&&o.tabItems.forEach(d=>{d.child&&s([d.child],i.id)});break;case"Modal":s([o.entryPointChild,o.contentChild],i.id);break;case"Button":o.child&&s([o.child],i.id);break}}}).describe("Updates a surface with a new set of components."),el=x.object({surfaceId:x.string().describe("The unique identifier for the UI surface this data model update applies to."),path:x.string().optional().describe("An optional path to a location within the data model (e.g., '/user/name'). If omitted, or set to '/', the entire data model will be replaced."),contents:x.array(Xo).describe("An array of data entries. Each entry must contain a 'key' and exactly one corresponding typed 'value*' property.")}).strict().describe("Updates the data model for a surface."),tl=x.object({surfaceId:x.string().describe("The unique identifier for the UI surface to be deleted.")}).strict().describe("Signals the client to delete the surface identified by 'surfaceId'."),Qi=x.object({beginRendering:Jo.optional(),surfaceUpdate:Qo.optional(),dataModelUpdate:el.optional(),deleteSurface:tl.optional()}).strict().superRefine((t,e)=>{Object.keys(t).filter(s=>["beginRendering","surfaceUpdate","dataModelUpdate","deleteSurface"].includes(s)).length!==1&&e.addIssue({code:x.ZodIssueCode.custom,message:"A2UI Protocol message must have exactly one of: surfaceUpdate, dataModelUpdate, beginRendering, deleteSurface."})}).describe("Describes a JSON payload for an A2UI message, which is used to dynamically construct and update user interfaces. A message MUST contain exactly ONE of the action properties: 'beginRendering', 'surfaceUpdate', 'dataModelUpdate', or 'deleteSurface'.");var Pr=class extends Error{constructor(e,r="UNKNOWN_ERROR"){super(e),this.name=this.constructor.name,this.code=r,Error.captureStackTrace&&Error.captureStackTrace(this,this.constructor)}},Y=class extends Pr{constructor(e,r){super(e,"VALIDATION_ERROR"),this.details=r}};var Dr=class extends Pr{constructor(e){super(e,"STATE_ERROR")}};var q=class t{constructor(e={mapCtor:Map,arrayCtor:Array,setCtor:Set,objCtor:Object}){this.opts=e,this.mapCtor=Map,this.arrayCtor=Array,this.setCtor=Set,this.objCtor=Object,this.arrayCtor=e.arrayCtor,this.mapCtor=e.mapCtor,this.setCtor=e.setCtor,this.objCtor=e.objCtor,this.surfaces=new e.mapCtor}getSurfaces(){let e=this.surfaces,r=new Map;for(let[s,i]of e)i.rootComponentId&&r.set(s,i);return r}clearSurfaces(){this.surfaces.clear()}processMessages(e){for(let r of e){let s=Qi.parse(r);s.beginRendering&&this.handleBeginRendering(s.beginRendering,s.beginRendering.surfaceId),s.surfaceUpdate&&this.handleSurfaceUpdate(s.surfaceUpdate,s.surfaceUpdate.surfaceId),s.dataModelUpdate&&this.handleDataModelUpdate(s.dataModelUpdate,s.dataModelUpdate.surfaceId),s.deleteSurface&&this.handleDeleteSurface(s.deleteSurface)}}getData(e,r,s=t.DEFAULT_SURFACE_ID){let i=this.getOrCreateSurface(s);if(!i)return null;let a;return r==="."||r===""?a=e.dataContextPath??"/":a=this.resolvePath(r,e.dataContextPath),this.getDataByPath(i.dataModel,a)}setData(e,r,s,i=t.DEFAULT_SURFACE_ID){if(!e){console.warn("No component node set");return}let a=this.getOrCreateSurface(i);if(!a)return;let n;r==="."||r===""?n=e.dataContextPath??"/":n=this.resolvePath(r,e.dataContextPath),this.setDataByPath(a.dataModel,n,s)}resolvePath(e,r){return e.startsWith("/")?e:r&&r!=="/"?r.endsWith("/")?`${r}${e}`:`${r}/${e}`:`/${e}`}parseIfJsonString(e){if(typeof e!="string")return e;let r=e.trim();if(r.startsWith("{")&&r.endsWith("}")||r.startsWith("[")&&r.endsWith("]"))try{return JSON.parse(e)}catch(s){return console.warn(`Failed to parse potential JSON string: "${e.substring(0,50)}..."`,s),e}return e}convertKeyValueArrayToMap(e){let r=new this.mapCtor;for(let s of e){if(!Z(s)||!("key"in s))continue;let i=s.key,a=this.findValueKey(s);if(!a)continue;let n=s[a];a==="valueMap"&&Array.isArray(n)?n=this.convertKeyValueArrayToMap(n):typeof n=="string"&&(n=this.parseIfJsonString(n)),this.setDataByPath(r,i,n)}return r}setDataByPath(e,r,s){if(Array.isArray(s)&&(s.length===0||Z(s[0])&&"key"in s[0]))if(s.length===1&&Z(s[0])&&s[0].key==="."){let d=s[0],u=this.findValueKey(d);u?(s=d[u],u==="valueMap"&&Array.isArray(s)?s=this.convertKeyValueArrayToMap(s):typeof s=="string"&&(s=this.parseIfJsonString(s))):s=this.convertKeyValueArrayToMap(s)}else s=this.convertKeyValueArrayToMap(s);let i=this.normalizePath(r).split("/").filter(d=>d);if(i.length===0){if(s instanceof Map||Z(s)){!(s instanceof Map)&&Z(s)&&(s=new this.mapCtor(Object.entries(s))),e.clear();for(let[d,u]of s.entries())e.set(d,u)}else console.error("Cannot set root of DataModel to a non-Map value.");return}let a=e;for(let d=0;d<i.length-1;d++){let u=i[d],c;a instanceof Map?c=a.get(u):Array.isArray(a)&&/^\d+$/.test(u)&&(c=a[parseInt(u,10)]),(c===void 0||typeof c!="object"||c===null)&&(c=new this.mapCtor,a instanceof this.mapCtor?a.set(u,c):Array.isArray(a)&&(a[parseInt(u,10)]=c)),a=c}let n=i[i.length-1],o=s;a instanceof this.mapCtor?a.set(n,o):Array.isArray(a)&&/^\d+$/.test(n)&&(a[parseInt(n,10)]=o)}normalizePath(e){return"/"+e.replace(/\[(\d+)\]/g,".$1").split(".").filter(i=>i.length>0).join("/")}getDataByPath(e,r){let s=this.normalizePath(r).split("/").filter(a=>a),i=e;for(let a of s){if(i==null)return null;if(i instanceof Map)i=i.get(a);else if(Array.isArray(i)&&/^\d+$/.test(a))i=i[parseInt(a,10)];else if(Z(i)){if(!Object.prototype.hasOwnProperty.call(i,a))return null;i=i[a]}else return null}return i}getOrCreateSurface(e){let r=this.surfaces.get(e);return r||(r=new this.objCtor({rootComponentId:null,componentTree:null,dataModel:new this.mapCtor,components:new this.mapCtor,styles:new this.objCtor}),this.surfaces.set(e,r)),r}handleBeginRendering(e,r){let s=this.getOrCreateSurface(r);s.rootComponentId=e.root,s.styles=e.styles??{},this.rebuildComponentTree(s)}handleSurfaceUpdate(e,r){let s=this.getOrCreateSurface(r);for(let i of e.components)s.components.set(i.id,i);this.rebuildComponentTree(s)}handleDataModelUpdate(e,r){let s=this.getOrCreateSurface(r),i=e.path??"/";this.setDataByPath(s.dataModel,i,e.contents),this.rebuildComponentTree(s)}handleDeleteSurface(e){this.surfaces.delete(e.surfaceId)}rebuildComponentTree(e){if(!e.rootComponentId){e.componentTree=null;return}let r=new this.setCtor;e.componentTree=this.buildNodeRecursive(e.rootComponentId,e,r,"/","")}findValueKey(e){return Object.keys(e).find(r=>r.startsWith("value"))}buildNodeRecursive(e,r,s,i,a=""){let n=`${e}${a}`,{components:o}=r;if(!o.has(e))return null;if(s.has(n))throw new Dr(`Circular dependency for component "${n}".`);s.add(n);let d=o.get(e),u=d.component??{},c=Object.keys(u)[0],l=u[c],p=new this.objCtor;if(Z(l))for(let[g,m]of Object.entries(l))p[g]=this.resolvePropertyValue(m,r,s,i,a,g==="action");s.delete(n);let h={id:n,dataContextPath:i,weight:d.weight??"initial"};switch(c){case"Text":if(!Os(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"Text",properties:p});case"Image":if(!Ss(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"Image",properties:p});case"Icon":if(!Cs(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"Icon",properties:p});case"Video":if(!Ps(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"Video",properties:p});case"AudioPlayer":if(!ys(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"AudioPlayer",properties:p});case"Row":if(!As(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"Row",properties:p});case"Column":if(!xs(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"Column",properties:p});case"List":if(!ks(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"List",properties:p});case"Card":if(!_s(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"Card",properties:p});case"Tabs":if(!Rs(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"Tabs",properties:p});case"Divider":if(!$s(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"Divider",properties:p});case"Modal":if(!Ts(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"Modal",properties:p});case"Button":if(!vs(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"Button",properties:p});case"CheckBox":if(!bs(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"CheckBox",properties:p});case"TextField":if(!js(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"TextField",properties:p});case"DateTimeInput":if(!ws(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"DateTimeInput",properties:p});case"MultipleChoice":if(!Es(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"MultipleChoice",properties:p});case"Slider":if(!Is(p))throw new Y(`Invalid data; expected ${c}`);return new this.objCtor({...h,type:"Slider",properties:p});default:return new this.objCtor({...h,type:c,properties:p})}}resolvePropertyValue(e,r,s,i,a="",n=!1){if(!n&&typeof e=="string"&&r.components.has(e))return this.buildNodeRecursive(e,r,s,i,a);if(!n&&gs(e)){if(e.explicitList)return e.explicitList.map(o=>this.buildNodeRecursive(o,r,s,i,a));if(e.template){let o=this.resolvePath(e.template.dataBinding,i),d=this.getDataByPath(r.dataModel,o),u=e.template;if(Array.isArray(d))return d.map((l,p)=>{let m=`:${[...i.split("/").filter(v=>/^\d+$/.test(v)),p].join(":")}`,f=`${o}/${p}`;return this.buildNodeRecursive(u.componentId,r,s,f,m)});let c=this.mapCtor;return d instanceof c?Array.from(d.keys(),l=>{let p=`:${l}`,h=`${o}/${l}`;return this.buildNodeRecursive(u.componentId,r,s,h,p)}):new this.arrayCtor}}if(Array.isArray(e))return e.map(o=>this.resolvePropertyValue(o,r,s,i,a,n));if(Z(e)){let o=new this.objCtor;for(let[d,u]of Object.entries(e)){let c=u;if(ms(d,u)&&i!=="/"){c=u.replace(/^\.?\/item/,"").replace(/^\.?\/text/,"").replace(/^\.?\/label/,"").replace(/^\.?\//,""),o[d]=c;continue}o[d]=this.resolvePropertyValue(c,r,s,i,a,n||d==="action")}return o}return e}};q.DEFAULT_SURFACE_ID="@default";var ke={};Ht(ke,{appendToAll:()=>il,createThemeStyles:()=>al,merge:()=>sl,structuralStyles:()=>Fs,toProp:()=>he});var rl=`
  &:not([disabled]) {
    cursor: pointer;
    opacity: var(--opacity, 0);
    transition: opacity var(--speed, 0.2s) cubic-bezier(0, 0, 0.3, 1);

    &:hover,
    &:focus {
      opacity: 1;
    }
  }`,ea=`
  ${new Array(21).fill(0).map((t,e)=>`.behavior-ho-${e*5} {
          --opacity: ${e/20};
          ${rl}
        }`).join(`
`)}

  .behavior-o-s {
    overflow: scroll;
  }

  .behavior-o-a {
    overflow: auto;
  }

  .behavior-o-h {
    overflow: hidden;
  }

  .behavior-sw-n {
    scrollbar-width: none;
  }
`;var ta=`
  ${new Array(25).fill(0).map((t,e)=>`
        .border-bw-${e} { border-width: ${e}px; }
        .border-btw-${e} { border-top-width: ${e}px; }
        .border-bbw-${e} { border-bottom-width: ${e}px; }
        .border-blw-${e} { border-left-width: ${e}px; }
        .border-brw-${e} { border-right-width: ${e}px; }

        .border-ow-${e} { outline-width: ${e}px; }
        .border-br-${e} { border-radius: ${e*4}px; overflow: hidden;}`).join(`
`)}

  .border-br-50pc {
    border-radius: 50%;
  }

  .border-bs-s {
    border-style: solid;
  }
`;var Us=[0,5,10,15,20,25,30,35,40,50,60,70,80,90,95,98,99,100];function sl(...t){let e={};for(let r of t)for(let[s,i]of Object.entries(r)){let a=s.split("-").with(-1,"").join("-"),n=Object.keys(e).filter(o=>o.startsWith(a));for(let o of n)delete e[o];e[s]=i}return e}function il(t,e,...r){let s=structuredClone(t);for(let i of r)for(let a of Object.keys(i)){let n=a.split("-").with(-1,"").join("-");for(let[o,d]of Object.entries(s)){if(e.includes(o))continue;let u=!1;for(let c=0;c<d.length;c++)d[c].startsWith(n)&&(u=!0,d[c]=a);u||d.push(a)}}return s}function al(t){let e={};for(let r of Object.values(t))for(let[s,i]of Object.entries(r)){let a=he(s);e[a]=i}return e}function he(t){return t.startsWith("nv")?`--nv-${t.slice(2)}`:`--${t[0]}-${t.slice(1)}`}var jt=t=>`
    ${t.map(e=>{let r=Ls(e);return`.color-bc-${e} { border-color: light-dark(var(${he(e)}), var(${he(r)})); }`}).join(`
`)}

    ${t.map(e=>{let r=Ls(e),s=[`.color-bgc-${e} { background-color: light-dark(var(${he(e)}), var(${he(r)})); }`,`.color-bbgc-${e}::backdrop { background-color: light-dark(var(${he(e)}), var(${he(r)})); }`];for(let i=.1;i<1;i+=.1)s.push(`.color-bbgc-${e}_${(i*100).toFixed(0)}::backdrop {
            background-color: light-dark(oklch(from var(${he(e)}) l c h / calc(alpha * ${i.toFixed(1)})), oklch(from var(${he(r)}) l c h / calc(alpha * ${i.toFixed(1)})) );
          }
        `);return s.join(`
`)}).join(`
`)}

  ${t.map(e=>{let r=Ls(e);return`.color-c-${e} { color: light-dark(var(${he(e)}), var(${he(r)})); }`}).join(`
`)}
  `,Ls=t=>{let e=t.match(/^([a-z]+)(\d+)$/);if(!e)return t;let[,r,s]=e,a=100-parseInt(s,10),n=Us.reduce((o,d)=>Math.abs(d-a)<Math.abs(o-a)?d:o);return`${r}${n}`},Pt=t=>Us.map(e=>`${t}${e}`),ra=[jt(Pt("p")),jt(Pt("s")),jt(Pt("t")),jt(Pt("n")),jt(Pt("nv")),jt(Pt("e")),`
    .color-bgc-transparent {
      background-color: transparent;
    }

    :host {
      color-scheme: var(--color-scheme);
    }
  `];var sa=`
  .g-icon {
    font-family: "Material Symbols Outlined", "Google Symbols";
    font-weight: normal;
    font-style: normal;
    font-display: optional;
    font-size: 24px;
    width: 1em;
    height: 1em;
    user-select: none;
    line-height: 1;
    letter-spacing: normal;
    text-transform: none;
    display: inline-block;
    white-space: nowrap;
    word-wrap: normal;
    direction: ltr;
    font-feature-settings: "liga";
    -webkit-font-feature-settings: "liga";
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
    -moz-osx-font-smoothing: grayscale;
    overflow: hidden;

    font-variation-settings: "FILL" 0, "wght" 300, "GRAD" 0, "opsz" 48,
      "ROND" 100;

    &.filled {
      font-variation-settings: "FILL" 1, "wght" 300, "GRAD" 0, "opsz" 48,
        "ROND" 100;
    }

    &.filled-heavy {
      font-variation-settings: "FILL" 1, "wght" 700, "GRAD" 0, "opsz" 48,
        "ROND" 100;
    }
  }
`;var ia=`
  :host {
    ${new Array(16).fill(0).map((t,e)=>`--g-${e+1}: ${(e+1)*4}px;`).join(`
`)}
  }

  ${new Array(49).fill(0).map((t,e)=>{let r=e-24,s=r<0?`n${Math.abs(r)}`:r.toString();return`
        .layout-p-${s} { --padding: ${r*4}px; padding: var(--padding); }
        .layout-pt-${s} { padding-top: ${r*4}px; }
        .layout-pr-${s} { padding-right: ${r*4}px; }
        .layout-pb-${s} { padding-bottom: ${r*4}px; }
        .layout-pl-${s} { padding-left: ${r*4}px; }

        .layout-m-${s} { --margin: ${r*4}px; margin: var(--margin); }
        .layout-mt-${s} { margin-top: ${r*4}px; }
        .layout-mr-${s} { margin-right: ${r*4}px; }
        .layout-mb-${s} { margin-bottom: ${r*4}px; }
        .layout-ml-${s} { margin-left: ${r*4}px; }

        .layout-t-${s} { top: ${r*4}px; }
        .layout-r-${s} { right: ${r*4}px; }
        .layout-b-${s} { bottom: ${r*4}px; }
        .layout-l-${s} { left: ${r*4}px; }`}).join(`
`)}

  ${new Array(25).fill(0).map((t,e)=>`
        .layout-g-${e} { gap: ${e*4}px; }`).join(`
`)}

  ${new Array(8).fill(0).map((t,e)=>`
        .layout-grd-col${e+1} { grid-template-columns: ${"1fr ".repeat(e+1).trim()}; }`).join(`
`)}

  .layout-pos-a {
    position: absolute;
  }

  .layout-pos-rel {
    position: relative;
  }

  .layout-dsp-none {
    display: none;
  }

  .layout-dsp-block {
    display: block;
  }

  .layout-dsp-grid {
    display: grid;
  }

  .layout-dsp-iflex {
    display: inline-flex;
  }

  .layout-dsp-flexvert {
    display: flex;
    flex-direction: column;
  }

  .layout-dsp-flexhor {
    display: flex;
    flex-direction: row;
  }

  .layout-fw-w {
    flex-wrap: wrap;
  }

  .layout-al-fs {
    align-items: start;
  }

  .layout-al-fe {
    align-items: end;
  }

  .layout-al-c {
    align-items: center;
  }

  .layout-as-n {
    align-self: normal;
  }

  .layout-js-c {
    justify-self: center;
  }

  .layout-sp-c {
    justify-content: center;
  }

  .layout-sp-ev {
    justify-content: space-evenly;
  }

  .layout-sp-bt {
    justify-content: space-between;
  }

  .layout-sp-s {
    justify-content: start;
  }

  .layout-sp-e {
    justify-content: end;
  }

  .layout-ji-e {
    justify-items: end;
  }

  .layout-r-none {
    resize: none;
  }

  .layout-fs-c {
    field-sizing: content;
  }

  .layout-fs-n {
    field-sizing: none;
  }

  .layout-flx-0 {
    flex: 0 0 auto;
  }

  .layout-flx-1 {
    flex: 1 0 auto;
  }

  .layout-c-s {
    contain: strict;
  }

  /** Widths **/

  ${new Array(10).fill(0).map((t,e)=>{let r=(e+1)*10;return`.layout-w-${r} { width: ${r}%; max-width: ${r}%; }`}).join(`
`)}

  ${new Array(16).fill(0).map((t,e)=>{let r=e*4;return`.layout-wp-${e} { width: ${r}px; }`}).join(`
`)}

  /** Heights **/

  ${new Array(10).fill(0).map((t,e)=>{let r=(e+1)*10;return`.layout-h-${r} { height: ${r}%; }`}).join(`
`)}

  ${new Array(16).fill(0).map((t,e)=>{let r=e*4;return`.layout-hp-${e} { height: ${r}px; }`}).join(`
`)}

  .layout-el-cv {
    & img,
    & video {
      width: 100%;
      height: 100%;
      object-fit: cover;
      margin: 0;
    }
  }

  .layout-ar-sq {
    aspect-ratio: 1 / 1;
  }

  .layout-ex-fb {
    margin: calc(var(--padding) * -1) 0 0 calc(var(--padding) * -1);
    width: calc(100% + var(--padding) * 2);
    height: calc(100% + var(--padding) * 2);
  }
`;var aa=`
  ${new Array(21).fill(0).map((t,e)=>`.opacity-el-${e*5} { opacity: ${e/20}; }`).join(`
`)}
`;var na=`
  :host {
    --default-font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    --default-font-family-mono: "Courier New", Courier, monospace;
  }

  .typography-f-s {
    font-family: var(--font-family, var(--default-font-family));
    font-optical-sizing: auto;
    font-variation-settings: "slnt" 0, "wdth" 100, "GRAD" 0;
  }

  .typography-f-sf {
    font-family: var(--font-family-flex, var(--default-font-family));
    font-optical-sizing: auto;
  }

  .typography-f-c {
    font-family: var(--font-family-mono, var(--default-font-family));
    font-optical-sizing: auto;
    font-variation-settings: "slnt" 0, "wdth" 100, "GRAD" 0;
  }

  .typography-v-r {
    font-variation-settings: "slnt" 0, "wdth" 100, "GRAD" 0, "ROND" 100;
  }

  .typography-ta-s {
    text-align: start;
  }

  .typography-ta-c {
    text-align: center;
  }

  .typography-fs-n {
    font-style: normal;
  }

  .typography-fs-i {
    font-style: italic;
  }

  .typography-sz-ls {
    font-size: 11px;
    line-height: 16px;
  }

  .typography-sz-lm {
    font-size: 12px;
    line-height: 16px;
  }

  .typography-sz-ll {
    font-size: 14px;
    line-height: 20px;
  }

  .typography-sz-bs {
    font-size: 12px;
    line-height: 16px;
  }

  .typography-sz-bm {
    font-size: 14px;
    line-height: 20px;
  }

  .typography-sz-bl {
    font-size: 16px;
    line-height: 24px;
  }

  .typography-sz-ts {
    font-size: 14px;
    line-height: 20px;
  }

  .typography-sz-tm {
    font-size: 16px;
    line-height: 24px;
  }

  .typography-sz-tl {
    font-size: 22px;
    line-height: 28px;
  }

  .typography-sz-hs {
    font-size: 24px;
    line-height: 32px;
  }

  .typography-sz-hm {
    font-size: 28px;
    line-height: 36px;
  }

  .typography-sz-hl {
    font-size: 32px;
    line-height: 40px;
  }

  .typography-sz-ds {
    font-size: 36px;
    line-height: 44px;
  }

  .typography-sz-dm {
    font-size: 45px;
    line-height: 52px;
  }

  .typography-sz-dl {
    font-size: 57px;
    line-height: 64px;
  }

  .typography-ws-p {
    white-space: pre-line;
  }

  .typography-ws-nw {
    white-space: nowrap;
  }

  .typography-td-none {
    text-decoration: none;
  }

  /** Weights **/

  ${new Array(9).fill(0).map((t,e)=>{let r=(e+1)*100;return`.typography-w-${r} { font-weight: ${r}; }`}).join(`
`)}
`;var Fs=[ea,ta,ra,sa,ia,aa,na].flat(1/0).join(`
`);var L=class extends Error{constructor(e,r=!1){super(e),this.name="RegexSyntaxError",this.unsupported=r}},be={start:55296,end:57343},Bs=1114111,Nr=65535,ua=[{start:48,end:57}],da=[{start:48,end:57},{start:65,end:90},{start:95,end:95},{start:97,end:122}],ha=[{start:9,end:13},{start:32,end:32},{start:160,end:160},{start:5760,end:5760},{start:8192,end:8202},{start:8232,end:8233},{start:8239,end:8239},{start:8287,end:8287},{start:12288,end:12288},{start:65279,end:65279}],nl=[{start:10,end:10},{start:13,end:13},{start:8232,end:8233}],ol=new Set([94,36,92,46,42,43,63,40,41,91,93,123,125,124,47]),ll=new Map([[116,9],[110,10],[118,11],[102,12],[114,13]]);function pa(t){if(t.start>t.end)return[];if(t.end<be.start||t.start>be.end)return[t];let e=[];return t.start<be.start&&e.push({start:t.start,end:be.start-1}),t.end>be.end&&e.push({start:be.end+1,end:t.end}),e}function Mt(t){let e=t.flatMap(pa);if(e.length<=1)return e;e.sort((s,i)=>s.start-i.start||s.end-i.end);let r=[e[0]];for(let s=1;s<e.length;s++){let i=r[r.length-1],a=e[s];a.start<=i.end+1?r[r.length-1]={start:i.start,end:Math.max(i.end,a.end)}:r.push(a)}return r}function Jt(t){let e=Mt([...t,be]),r=[],s=0;for(let i of e)i.start>s&&r.push({start:s,end:i.start-1}),s=i.end+1;return s<=Bs&&r.push({start:s,end:Bs}),r.flatMap(pa)}var cl=Jt(ua),ul=Jt(da),dl=Jt(ha),hl=Jt(nl),pl=new Map([[100,ua],[68,cl],[119,da],[87,ul],[115,ha],[83,dl]]);function fa(t,e){let r=0,s=0;for(;r<t.length&&s<e.length;)if(t[r].end<e[s].start)r++;else if(e[s].end<t[r].start)s++;else return!0;return!1}function Vr(t){let e=0;for(let r=0;r<t.length;r++){let s=t.charCodeAt(r);if(s>=55296&&s<=56319&&r+1<t.length){let i=t.charCodeAt(r+1);i>=56320&&i<=57343&&r++}e++}return e}function fl(t){let e=[];for(let r=0;r<t.length;r++){let s=t.charCodeAt(r);if(s>=55296&&s<=56319){let i=r+1<t.length?t.charCodeAt(r+1):0;if(i<56320||i>57343)throw new L("Lone high surrogate in pattern",!0);e.push(65536+(s-55296<<10)+(i-56320)),r++}else{if(s>=56320&&s<=57343)throw new L("Lone low surrogate in pattern",!0);e.push(s)}}return e}var Hs=class{constructor(e){this.cps=e,this.pos=0}eof(){return this.pos>=this.cps.length}peek(e=0){return this.cps[this.pos+e]}next(){if(this.pos>=this.cps.length)throw new L("Unexpected end of pattern",!1);return this.cps[this.pos++]}eat(e){return this.cps[this.pos]===e?(this.pos++,!0):!1}};function qs(t){return t!==void 0&&t>=48&&t<=57}function ma(t){return t===void 0?-1:t>=48&&t<=57?t-48:t>=65&&t<=70?t-65+10:t>=97&&t<=102?t-97+10:-1}function ga(t,e){let r=0;for(let s=0;s<e;s++){let i=ma(t.peek());if(i<0)throw new L("Invalid hexadecimal escape",!1);t.next(),r=r<<4|i}return r}function ml(t){if(!t.eat(123)){let s=ga(t,4);if(s>=be.start&&s<=be.end)throw new L("Surrogate code point escape is not supported",!0);return s}let e=0,r=0;for(;!t.eof()&&t.peek()!==125;){let s=ma(t.peek());if(s<0)throw new L("Invalid braced Unicode escape",!1);if(t.next(),e=e*16+s,r++,e>Bs)throw new L("Unicode escape exceeds U+10FFFF",!1)}if(r===0||!t.eat(125))throw new L("Malformed braced Unicode escape",!1);if(e>=be.start&&e<=be.end)throw new L("Surrogate code point escape is not supported",!0);return e}function gl(t,e){if(e===48){if(qs(t.peek()))throw new L("Octal escape is not supported",!0);return 0}if(e>=49&&e<=57)throw new L("Backreference or octal escape is not supported",!0);return e===120?ga(t,2):e===117?ml(t):null}function ya(t,e){if(t.eof())throw new L("Trailing backslash in pattern",!1);let r=t.next();if(r===98)return e?{kind:"single",cp:8}:{kind:"anchor",anchor:"wordBoundary"};if(r===66){if(e)throw new L("\\B is not supported inside a character class",!0);return{kind:"anchor",anchor:"notWordBoundary"}}let s=pl.get(r);if(s!==void 0)return{kind:"ranges",ranges:s};let i=ll.get(r);if(i!==void 0)return{kind:"single",cp:i};let a=gl(t,r);if(a!==null)return{kind:"single",cp:a};if(ol.has(r)||e&&r===45)return{kind:"single",cp:r};throw new L("Unsupported escape sequence",!0)}function oa(t){let e=t.peek();if(e===92){t.next();let s=ya(t,!0);if(s.kind==="single")return{single:s.cp,ranges:[{start:s.cp,end:s.cp}]};if(s.kind==="ranges")return{ranges:s.ranges};throw new L("Assertions are not valid in a character class",!0)}if(e===91)throw new L("Nested character class is not supported",!0);if(e===38&&t.peek(1)===38)throw new L("Character class intersection is not supported",!0);let r=t.next();return{single:r,ranges:[{start:r,end:r}]}}function yl(t){let e=oa(t);if(t.peek()!==45||t.peek(1)===93)return e.ranges;if(t.next(),t.peek()===45)throw new L("Character class subtraction is not supported",!0);let r=oa(t);if(e.single===void 0||r.single===void 0)throw new L("Character class escape cannot form a range",!1);if(e.single>r.single)throw new L("Character class range out of order",!1);return[{start:e.single,end:r.single}]}function vl(t){let e=t.eat(94),r=[];for(;!t.eof()&&t.peek()!==93;)r.push(...yl(t));if(!t.eat(93))throw new L("Unclosed character class",!1);if(r.length===0)throw new L("Empty character class",!1);let s=Mt(r);return{kind:"charSet",ranges:e?Jt(s):s}}function la(t){if(!qs(t.peek()))return null;let e=0;for(;qs(t.peek());)e=e*10+(t.next()-48);return e}function _l(t){let e=la(t);if(e===null)throw new L("Malformed brace quantifier",!0);if(e>Nr)throw new L(`Quantifier lower bound ${e} exceeds ${Nr}`,!1);if(t.eat(125))return{min:e,max:e};if(!t.eat(44))throw new L("Malformed brace quantifier",!0);if(t.eat(125))return{min:e,max:null};let r=la(t);if(r===null||!t.eat(125))throw new L("Malformed brace quantifier",!0);if(r>Nr)throw new L(`Quantifier upper bound ${r} exceeds ${Nr}`,!1);if(r<e)throw new L("Quantifier minimum exceeds maximum",!1);return{min:e,max:r}}function va(t){return t===42||t===43||t===63||t===123}function bl(t,e){let r=t.next(),s=0,i=null;if(r===42)s=0,i=null;else if(r===43)s=1,i=null;else if(r===63)s=0,i=1;else{let n=_l(t);s=n.min,i=n.max}let a=t.eat(63);if(va(t.peek()))throw new L("Possessive or chained quantifiers are not supported",!0);return{kind:"repeat",child:e,min:s,max:i,lazy:a}}function xl(t){if(!t.eat(63)){let s=Ws(t);if(!t.eat(41))throw new L("Unclosed group",!1);return{kind:"group",capturing:!0,child:s}}let e=t.peek();if(e!==58&&e!==61&&e!==33)throw new L("Unsupported group extension",!0);t.next();let r=Ws(t);if(!t.eat(41))throw new L("Unclosed group",!1);return e===58?{kind:"group",capturing:!1,child:r}:{kind:"lookahead",negated:e===33,child:r}}function wl(t){let e=t.next();if(e===94)return{kind:"anchor",anchor:"start"};if(e===36)return{kind:"anchor",anchor:"end"};if(e===46)return{kind:"charSet",ranges:hl};if(e===91)return vl(t);if(e===40)return xl(t);if(e===92){let r=ya(t,!1);return r.kind==="anchor"?{kind:"anchor",anchor:r.anchor}:r.kind==="ranges"?{kind:"charSet",ranges:r.ranges}:{kind:"charSet",ranges:[{start:r.cp,end:r.cp}]}}if(e===123||e===125||e===93)throw new L("Unescaped brace or bracket is not supported",!0);if(e===42||e===43||e===63)throw new L("Nothing to repeat",!1);return{kind:"charSet",ranges:[{start:e,end:e}]}}function $l(t){let e=wl(t);if(!va(t.peek()))return e;if(e.kind==="anchor"||e.kind==="lookahead")throw new L("Quantifier on an assertion is not supported",!0);return bl(t,e)}function ca(t){let e=[];for(;!t.eof()&&t.peek()!==124&&t.peek()!==41;)e.push($l(t));return e.length===0?{kind:"empty"}:e.length===1?e[0]:{kind:"concat",items:e}}function Ws(t){let e=[ca(t)];for(;t.eat(124);)e.push(ca(t));return e.length===1?e[0]:{kind:"alt",branches:e}}function Sl(t){let e=new Hs(fl(t)),r=Ws(e);if(!e.eof())throw new L("Unmatched closing parenthesis",!1);return r}function zr(t){let e=t;for(;e.kind==="group";)e=e.child;return e}function Dt(t){switch(t.kind){case"empty":case"anchor":case"lookahead":return!0;case"charSet":return!1;case"group":return Dt(t.child);case"repeat":return t.min===0||Dt(t.child);case"concat":return t.items.every(Dt);case"alt":return t.branches.some(Dt)}}function Gt(t){switch(t.kind){case"empty":case"anchor":case"lookahead":return[];case"charSet":return t.ranges;case"group":return Gt(t.child);case"repeat":return t.max===0?[]:Gt(t.child);case"alt":return Mt(t.branches.flatMap(Gt));case"concat":{let e=[];for(let r of t.items)if(e.push(...Gt(r)),!Dt(r))break;return Mt(e)}}}function Nt(t){switch(t.kind){case"empty":case"anchor":case"lookahead":return[];case"charSet":return t.ranges;case"group":return Nt(t.child);case"repeat":return t.max===0?[]:Nt(t.child);case"concat":return Mt(t.items.flatMap(Nt));case"alt":return Mt(t.branches.flatMap(Nt))}}function Xt(t){switch(t.kind){case"empty":case"charSet":case"anchor":return!1;case"group":case"lookahead":return Xt(t.child);case"repeat":return t.max===null||Xt(t.child);case"concat":return t.items.some(Xt);case"alt":return t.branches.some(Xt)}}function Kt(t){switch(t.kind){case"empty":case"charSet":case"anchor":return!1;case"group":case"lookahead":return Kt(t.child);case"repeat":return(t.max===null||t.max>1)&&Xt(t.child)?!0:Kt(t.child);case"concat":return t.items.some(Kt);case"alt":return t.branches.some(Kt)}}function Cl(t){let e=t.map(r=>Gt(zr(r)));for(let r=0;r<e.length;r++)for(let s=r+1;s<e.length;s++)if(fa(e[r],e[s]))return!0;return!1}function Yt(t){switch(t.kind){case"empty":case"charSet":case"anchor":return!1;case"group":case"lookahead":return Yt(t.child);case"repeat":{let e=zr(t.child);return t.max===null&&e.kind==="alt"&&Cl(e.branches)?!0:Yt(t.child)}case"concat":return t.items.some(Yt);case"alt":return t.branches.some(Yt)}}function kl(t){for(let e=0;e<t.length;e++){let r=zr(t[e]);if(r.kind!=="repeat"||r.max!==null)continue;let s=Nt(r.child);for(let i=e+1;i<t.length;i++){let a=zr(t[i]);if(a.kind==="repeat"&&a.max===null&&fa(s,Nt(a.child)))return!0;if(!Dt(t[i]))break}}return!1}function Mr(t){switch(t.kind){case"empty":case"charSet":case"anchor":return!1;case"group":case"lookahead":case"repeat":return Mr(t.child);case"concat":return kl(t.items)||t.items.some(Mr);case"alt":return t.branches.some(Mr)}}function Tl(t,e){return Vr(t)>256?"PATTERN_TOO_LONG":Kt(e)?"NESTED_QUANTIFIER":Yt(e)?"OVERLAPPING_ALTERNATION":Mr(e)?"ADJACENT_OVERLAP":null}function _a(t){if(Vr(t)>256)return{ok:!1,reason:"PATTERN_TOO_LONG",detail:"Pattern exceeds maximum length of 256 code points"};let e;try{e=Sl(t)}catch(s){if(s instanceof L)return{ok:!1,reason:"UNSUPPORTED_SYNTAX",detail:s.message};throw s}let r=Tl(t,e);return r!==null?{ok:!1,reason:r,detail:`Unsafe regex pattern (${r})`}:{ok:!0,tree:e}}function Zs(t,e={}){if(t==null||typeof t!="string"||t.length===0)return!0;let r=e.maxPatternLength??256;return Vr(t)>r?!1:_a(t).ok}function ba(t,e){return Object.is(t,e)}var Q=null,Qt=!1,Ur=1,Lr=Symbol("SIGNAL");function zt(t){let e=Q;return Q=t,e}function Al(){return Q}function Il(){return Qt}var Js={version:0,lastCleanEpoch:0,dirty:!1,producerNode:void 0,producerLastReadVersion:void 0,producerIndexOfThis:void 0,nextProducerIndex:0,liveConsumerNode:void 0,liveConsumerIndexOfThis:void 0,consumerAllowSignalWrites:!1,consumerIsAlwaysLive:!1,producerMustRecompute:()=>!1,producerRecomputeValue:()=>{},consumerMarkedDirty:()=>{},consumerOnSignalRead:()=>{}};function Fr(t){if(Qt)throw new Error(typeof ngDevMode<"u"&&ngDevMode?"Assertion error: signal read during notification phase":"");if(Q===null)return;Q.consumerOnSignalRead(t);let e=Q.nextProducerIndex++;if(Vt(Q),e<Q.producerNode.length&&Q.producerNode[e]!==t&&Ks(Q)){let r=Q.producerNode[e];Br(r,Q.producerIndexOfThis[e])}Q.producerNode[e]!==t&&(Q.producerNode[e]=t,Q.producerIndexOfThis[e]=Ks(Q)?$a(t,Q,e):0),Q.producerLastReadVersion[e]=t.version}function Rl(){Ur++}function xa(t){if(!(!t.dirty&&t.lastCleanEpoch===Ur)){if(!t.producerMustRecompute(t)&&!Nl(t)){t.dirty=!1,t.lastCleanEpoch=Ur;return}t.producerRecomputeValue(t),t.dirty=!1,t.lastCleanEpoch=Ur}}function wa(t){if(t.liveConsumerNode===void 0)return;let e=Qt;Qt=!0;try{for(let r of t.liveConsumerNode)r.dirty||jl(r)}finally{Qt=e}}function Ol(){return Q?.consumerAllowSignalWrites!==!1}function jl(t){t.dirty=!0,wa(t),t.consumerMarkedDirty?.call(t.wrapper??t)}function Pl(t){return t&&(t.nextProducerIndex=0),zt(t)}function Dl(t,e){if(zt(e),!(!t||t.producerNode===void 0||t.producerIndexOfThis===void 0||t.producerLastReadVersion===void 0)){if(Ks(t))for(let r=t.nextProducerIndex;r<t.producerNode.length;r++)Br(t.producerNode[r],t.producerIndexOfThis[r]);for(;t.producerNode.length>t.nextProducerIndex;)t.producerNode.pop(),t.producerLastReadVersion.pop(),t.producerIndexOfThis.pop()}}function Nl(t){Vt(t);for(let e=0;e<t.producerNode.length;e++){let r=t.producerNode[e],s=t.producerLastReadVersion[e];if(s!==r.version||(xa(r),s!==r.version))return!0}return!1}function $a(t,e,r){if(Qs(t),Vt(t),t.liveConsumerNode.length===0){t.watched?.call(t.wrapper);for(let s=0;s<t.producerNode.length;s++)t.producerIndexOfThis[s]=$a(t.producerNode[s],t,s)}return t.liveConsumerIndexOfThis.push(r),t.liveConsumerNode.push(e)-1}function Br(t,e){if(Qs(t),Vt(t),typeof ngDevMode<"u"&&ngDevMode&&e>=t.liveConsumerNode.length)throw new Error(`Assertion error: active consumer index ${e} is out of bounds of ${t.liveConsumerNode.length} consumers)`);if(t.liveConsumerNode.length===1){t.unwatched?.call(t.wrapper);for(let s=0;s<t.producerNode.length;s++)Br(t.producerNode[s],t.producerIndexOfThis[s])}let r=t.liveConsumerNode.length-1;if(t.liveConsumerNode[e]=t.liveConsumerNode[r],t.liveConsumerIndexOfThis[e]=t.liveConsumerIndexOfThis[r],t.liveConsumerNode.length--,t.liveConsumerIndexOfThis.length--,e<t.liveConsumerNode.length){let s=t.liveConsumerIndexOfThis[e],i=t.liveConsumerNode[e];Vt(i),i.producerIndexOfThis[s]=e}}function Ks(t){return t.consumerIsAlwaysLive||(t?.liveConsumerNode?.length??0)>0}function Vt(t){t.producerNode??=[],t.producerIndexOfThis??=[],t.producerLastReadVersion??=[]}function Qs(t){t.liveConsumerNode??=[],t.liveConsumerIndexOfThis??=[]}function Sa(t){if(xa(t),Fr(t),t.value===Ys)throw t.error;return t.value}function Ml(t){let e=Object.create(zl);e.computation=t;let r=()=>Sa(e);return r[Lr]=e,r}var Gs=Symbol("UNSET"),Xs=Symbol("COMPUTING"),Ys=Symbol("ERRORED"),zl={...Js,value:Gs,dirty:!0,error:null,equal:ba,producerMustRecompute(t){return t.value===Gs||t.value===Xs},producerRecomputeValue(t){if(t.value===Xs)throw new Error("Detected cycle in computations.");let e=t.value;t.value=Xs;let r=Pl(t),s,i=!1;try{s=t.computation.call(t.wrapper),i=e!==Gs&&e!==Ys&&t.equal.call(t.wrapper,e,s)}catch(a){s=Ys,t.error=a}finally{Dl(t,r)}if(i){t.value=e;return}t.value=s,t.version++}};function Vl(){throw new Error}var Ul=Vl;function Ll(){Ul()}function Fl(t){let e=Object.create(ql);e.value=t;let r=()=>(Fr(e),e.value);return r[Lr]=e,r}function Bl(){return Fr(this),this.value}function Hl(t,e){Ol()||Ll(),t.equal.call(t.wrapper,t.value,e)||(t.value=e,Wl(t))}var ql={...Js,equal:ba,value:void 0};function Wl(t){t.version++,Rl(),wa(t)}var se=Symbol("node"),G;(t=>{class e{[se];#e(){}static{t.isState=i=>typeof i=="object"&&#e in i}constructor(i,a={}){let o=Fl(i)[Lr];if(this[se]=o,o.wrapper=this,a){let d=a.equals;d&&(o.equal=d),o.watched=a[t.subtle.watched],o.unwatched=a[t.subtle.unwatched]}}get(){if(!(0,t.isState)(this))throw new TypeError("Wrong receiver type for Signal.State.prototype.get");return Bl.call(this[se])}set(i){if(!(0,t.isState)(this))throw new TypeError("Wrong receiver type for Signal.State.prototype.set");if(Il())throw new Error("Writes to signals not permitted during Watcher callback");let a=this[se];Hl(a,i)}}t.State=e;class r{[se];#e(){}static{t.isComputed=i=>typeof i=="object"&&#e in i}constructor(i,a){let o=Ml(i)[Lr];if(o.consumerAllowSignalWrites=!0,this[se]=o,o.wrapper=this,a){let d=a.equals;d&&(o.equal=d),o.watched=a[t.subtle.watched],o.unwatched=a[t.subtle.unwatched]}}get(){if(!(0,t.isComputed)(this))throw new TypeError("Wrong receiver type for Signal.Computed.prototype.get");return Sa(this[se])}}t.Computed=r,(s=>{function i(l){let p,h=null;try{h=zt(null),p=l()}finally{zt(h)}return p}s.untrack=i;function a(l){if(!(0,t.isComputed)(l)&&!(0,t.isWatcher)(l))throw new TypeError("Called introspectSources without a Computed or Watcher argument");return l[se].producerNode?.map(p=>p.wrapper)??[]}s.introspectSources=a;function n(l){if(!(0,t.isComputed)(l)&&!(0,t.isState)(l))throw new TypeError("Called introspectSinks without a Signal argument");return l[se].liveConsumerNode?.map(p=>p.wrapper)??[]}s.introspectSinks=n;function o(l){if(!(0,t.isComputed)(l)&&!(0,t.isState)(l))throw new TypeError("Called hasSinks without a Signal argument");let p=l[se].liveConsumerNode;return p?p.length>0:!1}s.hasSinks=o;function d(l){if(!(0,t.isComputed)(l)&&!(0,t.isWatcher)(l))throw new TypeError("Called hasSources without a Computed or Watcher argument");let p=l[se].producerNode;return p?p.length>0:!1}s.hasSources=d;class u{[se];#e(){}static{t.isWatcher=p=>#e in p}constructor(p){let h=Object.create(Js);h.wrapper=this,h.consumerMarkedDirty=p,h.consumerIsAlwaysLive=!0,h.consumerAllowSignalWrites=!1,h.producerNode=[],this[se]=h}#t(p){for(let h of p)if(!(0,t.isComputed)(h)&&!(0,t.isState)(h))throw new TypeError("Called watch/unwatch without a Computed or State argument")}watch(...p){if(!(0,t.isWatcher)(this))throw new TypeError("Called unwatch without Watcher receiver");this.#t(p);let h=this[se];h.dirty=!1;let g=zt(h);for(let m of p)Fr(m[se]);zt(g)}unwatch(...p){if(!(0,t.isWatcher)(this))throw new TypeError("Called unwatch without Watcher receiver");this.#t(p);let h=this[se];Vt(h);for(let g=h.producerNode.length-1;g>=0;g--)if(p.includes(h.producerNode[g].wrapper)){Br(h.producerNode[g],h.producerIndexOfThis[g]);let m=h.producerNode.length-1;if(h.producerNode[g]=h.producerNode[m],h.producerIndexOfThis[g]=h.producerIndexOfThis[m],h.producerNode.length--,h.producerIndexOfThis.length--,h.nextProducerIndex--,g<h.producerNode.length){let f=h.producerIndexOfThis[g],v=h.producerNode[g];Qs(v),v.liveConsumerIndexOfThis[f]=g}}}getPending(){if(!(0,t.isWatcher)(this))throw new TypeError("Called getPending without Watcher receiver");return this[se].producerNode.filter(h=>h.dirty).map(h=>h.wrapper)}}s.Watcher=u;function c(){return Al()?.wrapper}s.currentComputed=c,s.watched=Symbol("watched"),s.unwatched=Symbol("unwatched")})(t.subtle||(t.subtle={}))})(G||(G={}));var ye=(t=null)=>new G.State(t,{equals:()=>!1});var Zl=new Set([Symbol.iterator,"concat","entries","every","filter","find","findIndex","flat","flatMap","forEach","includes","indexOf","join","keys","lastIndexOf","map","reduce","reduceRight","slice","some","values"]),Gl=new Set(["fill","push","unshift"]);function Ca(t){if(typeof t=="symbol")return null;let e=Number(t);return isNaN(e)?null:e%1===0?e:null}var er=class t{static from(e,r,s){return r?new t(Array.from(e,r,s)):new t(Array.from(e))}static of(...e){return new t(e)}constructor(e=[]){let r=e.slice(),s=this,i=new Map,a=!1;return new Proxy(r,{get(n,o){let d=Ca(o);if(d!==null)return s.#s(d),s.#e.get(),n[d];if(o==="length")return a?a=!1:s.#e.get(),n[o];if(Gl.has(o)&&(a=!0),Zl.has(o)){let u=i.get(o);return u===void 0&&(u=(...c)=>(s.#e.get(),n[o](...c)),i.set(o,u)),u}return n[o]},set(n,o,d){n[o]=d;let u=Ca(o);return u!==null?(s.#r(u),s.#e.set(null)):o==="length"&&s.#e.set(null),!0},getPrototypeOf(){return t.prototype}})}#e=ye();#t=new Map;#s(e){let r=this.#t.get(e);r===void 0&&(r=ye(),this.#t.set(e,r)),r.get()}#r(e){let r=this.#t.get(e);r&&r.set(null)}};Object.setPrototypeOf(er.prototype,Array.prototype);var tr=class{collection=ye();storages=new Map;vals;readStorageFor(e){let{storages:r}=this,s=r.get(e);s===void 0&&(s=ye(),r.set(e,s)),s.get()}dirtyStorageFor(e){let r=this.storages.get(e);r&&r.set(null)}constructor(e){this.vals=e?new Map(e):new Map}get(e){return this.readStorageFor(e),this.vals.get(e)}has(e){return this.readStorageFor(e),this.vals.has(e)}entries(){return this.collection.get(),this.vals.entries()}keys(){return this.collection.get(),this.vals.keys()}values(){return this.collection.get(),this.vals.values()}forEach(e){this.collection.get(),this.vals.forEach(e)}get size(){return this.collection.get(),this.vals.size}[Symbol.iterator](){return this.collection.get(),this.vals[Symbol.iterator]()}get[Symbol.toStringTag](){return this.vals[Symbol.toStringTag]}set(e,r){return this.dirtyStorageFor(e),this.collection.set(null),this.vals.set(e,r),this}delete(e){return this.dirtyStorageFor(e),this.collection.set(null),this.vals.delete(e)}clear(){this.storages.forEach(e=>e.set(null)),this.collection.set(null),this.vals.clear()}};Object.setPrototypeOf(tr.prototype,Map.prototype);var ei=class t{static fromEntries(e){return new t(Object.fromEntries(e))}#e=new Map;#t=ye();constructor(e={}){let r=Object.getPrototypeOf(e),s=Object.getOwnPropertyDescriptors(e),i=Object.create(r);for(let n in s)Object.defineProperty(i,n,s[n]);let a=this;return new Proxy(i,{get(n,o,d){return a.#s(o),Reflect.get(n,o,d)},has(n,o){return a.#s(o),o in n},ownKeys(n){return a.#t.get(),Reflect.ownKeys(n)},set(n,o,d,u){let c=Reflect.set(n,o,d,u);return a.#r(o),a.#i(),c},deleteProperty(n,o){return o in n&&(delete n[o],a.#r(o),a.#i()),!0},getPrototypeOf(){return t.prototype}})}#s(e){let r=this.#e.get(e);r===void 0&&(r=ye(),this.#e.set(e,r)),r.get()}#r(e){let r=this.#e.get(e);r&&r.set(null)}#i(){this.#t.set(null)}},ka=ei;var rr=class{collection=ye();storages=new Map;vals;storageFor(e){let r=this.storages,s=r.get(e);return s===void 0&&(s=ye(),r.set(e,s)),s}dirtyStorageFor(e){let r=this.storages.get(e);r&&r.set(null)}constructor(e){this.vals=new Set(e)}has(e){return this.storageFor(e).get(),this.vals.has(e)}entries(){return this.collection.get(),this.vals.entries()}keys(){return this.collection.get(),this.vals.keys()}values(){return this.collection.get(),this.vals.values()}forEach(e){this.collection.get(),this.vals.forEach(e)}get size(){return this.collection.get(),this.vals.size}[Symbol.iterator](){return this.collection.get(),this.vals[Symbol.iterator]()}get[Symbol.toStringTag](){return this.vals[Symbol.toStringTag]}add(e){return this.dirtyStorageFor(e),this.collection.set(null),this.vals.add(e),this}delete(e){return this.dirtyStorageFor(e),this.collection.set(null),this.vals.delete(e)}clear(){this.storages.forEach(e=>e.set(null)),this.collection.set(null),this.vals.clear()}};Object.setPrototypeOf(rr.prototype,Set.prototype);function Ta(){return new q({arrayCtor:er,mapCtor:tr,objCtor:ka,setCtor:rr})}var Ea={createSignalA2uiMessageProcessor:Ta,A2uiMessageProcessor:q,Guards:Ds};var Hr=globalThis,qr=Hr.ShadowRoot&&(Hr.ShadyCSS===void 0||Hr.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,ti=Symbol(),Aa=new WeakMap,sr=class{constructor(e,r,s){if(this._$cssResult$=!0,s!==ti)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=r}get styleSheet(){let e=this.o,r=this.t;if(qr&&e===void 0){let s=r!==void 0&&r.length===1;s&&(e=Aa.get(r)),e===void 0&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),s&&Aa.set(r,e))}return e}toString(){return this.cssText}},Ia=t=>new sr(typeof t=="string"?t:t+"",void 0,ti),z=(t,...e)=>{let r=t.length===1?t[0]:e.reduce((s,i,a)=>s+(n=>{if(n._$cssResult$===!0)return n.cssText;if(typeof n=="number")return n;throw Error("Value passed to 'css' function must be a 'css' function result: "+n+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+t[a+1],t[0]);return new sr(r,t,ti)},Ra=(t,e)=>{if(qr)t.adoptedStyleSheets=e.map(r=>r instanceof CSSStyleSheet?r:r.styleSheet);else for(let r of e){let s=document.createElement("style"),i=Hr.litNonce;i!==void 0&&s.setAttribute("nonce",i),s.textContent=r.cssText,t.appendChild(s)}},ri=qr?t=>t:t=>t instanceof CSSStyleSheet?(e=>{let r="";for(let s of e.cssRules)r+=s.cssText;return Ia(r)})(t):t;var{is:Xl,defineProperty:Kl,getOwnPropertyDescriptor:Yl,getOwnPropertyNames:Jl,getOwnPropertySymbols:Ql,getPrototypeOf:ec}=Object,Wr=globalThis,Oa=Wr.trustedTypes,tc=Oa?Oa.emptyScript:"",rc=Wr.reactiveElementPolyfillSupport,ir=(t,e)=>t,ar={toAttribute(t,e){switch(e){case Boolean:t=t?tc:null;break;case Object:case Array:t=t==null?t:JSON.stringify(t)}return t},fromAttribute(t,e){let r=t;switch(e){case Boolean:r=t!==null;break;case Number:r=t===null?null:Number(t);break;case Object:case Array:try{r=JSON.parse(t)}catch{r=null}}return r}},Zr=(t,e)=>!Xl(t,e),ja={attribute:!0,type:String,converter:ar,reflect:!1,useDefault:!1,hasChanged:Zr};Symbol.metadata??=Symbol("metadata"),Wr.litPropertyMetadata??=new WeakMap;var Pe=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,r=ja){if(r.state&&(r.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(e)&&((r=Object.create(r)).wrapped=!0),this.elementProperties.set(e,r),!r.noAccessor){let s=Symbol(),i=this.getPropertyDescriptor(e,s,r);i!==void 0&&Kl(this.prototype,e,i)}}static getPropertyDescriptor(e,r,s){let{get:i,set:a}=Yl(this.prototype,e)??{get(){return this[r]},set(n){this[r]=n}};return{get:i,set(n){let o=i?.call(this);a?.call(this,n),this.requestUpdate(e,o,s)},configurable:!0,enumerable:!0}}static getPropertyOptions(e){return this.elementProperties.get(e)??ja}static _$Ei(){if(this.hasOwnProperty(ir("elementProperties")))return;let e=ec(this);e.finalize(),e.l!==void 0&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(ir("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(ir("properties"))){let r=this.properties,s=[...Jl(r),...Ql(r)];for(let i of s)this.createProperty(i,r[i])}let e=this[Symbol.metadata];if(e!==null){let r=litPropertyMetadata.get(e);if(r!==void 0)for(let[s,i]of r)this.elementProperties.set(s,i)}this._$Eh=new Map;for(let[r,s]of this.elementProperties){let i=this._$Eu(r,s);i!==void 0&&this._$Eh.set(i,r)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){let r=[];if(Array.isArray(e)){let s=new Set(e.flat(1/0).reverse());for(let i of s)r.unshift(ri(i))}else e!==void 0&&r.push(ri(e));return r}static _$Eu(e,r){let s=r.attribute;return s===!1?void 0:typeof s=="string"?s:typeof e=="string"?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),this.renderRoot!==void 0&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){let e=new Map,r=this.constructor.elementProperties;for(let s of r.keys())this.hasOwnProperty(s)&&(e.set(s,this[s]),delete this[s]);e.size>0&&(this._$Ep=e)}createRenderRoot(){let e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Ra(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,r,s){this._$AK(e,s)}_$ET(e,r){let s=this.constructor.elementProperties.get(e),i=this.constructor._$Eu(e,s);if(i!==void 0&&s.reflect===!0){let a=(s.converter?.toAttribute!==void 0?s.converter:ar).toAttribute(r,s.type);this._$Em=e,a==null?this.removeAttribute(i):this.setAttribute(i,a),this._$Em=null}}_$AK(e,r){let s=this.constructor,i=s._$Eh.get(e);if(i!==void 0&&this._$Em!==i){let a=s.getPropertyOptions(i),n=typeof a.converter=="function"?{fromAttribute:a.converter}:a.converter?.fromAttribute!==void 0?a.converter:ar;this._$Em=i;let o=n.fromAttribute(r,a.type);this[i]=o??this._$Ej?.get(i)??o,this._$Em=null}}requestUpdate(e,r,s,i=!1,a){if(e!==void 0){let n=this.constructor;if(i===!1&&(a=this[e]),s??=n.getPropertyOptions(e),!((s.hasChanged??Zr)(a,r)||s.useDefault&&s.reflect&&a===this._$Ej?.get(e)&&!this.hasAttribute(n._$Eu(e,s))))return;this.C(e,r,s)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(e,r,{useDefault:s,reflect:i,wrapped:a},n){s&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,n??r??this[e]),a!==!0||n!==void 0)||(this._$AL.has(e)||(this.hasUpdated||s||(r=void 0),this._$AL.set(e,r)),i===!0&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(r){Promise.reject(r)}let e=this.scheduleUpdate();return e!=null&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[i,a]of this._$Ep)this[i]=a;this._$Ep=void 0}let s=this.constructor.elementProperties;if(s.size>0)for(let[i,a]of s){let{wrapped:n}=a,o=this[i];n!==!0||this._$AL.has(i)||o===void 0||this.C(i,void 0,a,o)}}let e=!1,r=this._$AL;try{e=this.shouldUpdate(r),e?(this.willUpdate(r),this._$EO?.forEach(s=>s.hostUpdate?.()),this.update(r)):this._$EM()}catch(s){throw e=!1,this._$EM(),s}e&&this._$AE(r)}willUpdate(e){}_$AE(e){this._$EO?.forEach(r=>r.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return!0}update(e){this._$Eq&&=this._$Eq.forEach(r=>this._$ET(r,this[r])),this._$EM()}updated(e){}firstUpdated(e){}};Pe.elementStyles=[],Pe.shadowRootOptions={mode:"open"},Pe[ir("elementProperties")]=new Map,Pe[ir("finalized")]=new Map,rc?.({ReactiveElement:Pe}),(Wr.reactiveElementVersions??=[]).push("2.1.2");var ii=globalThis,Pa=t=>t,Gr=ii.trustedTypes,Da=Gr?Gr.createPolicy("lit-html",{createHTML:t=>t}):void 0,ai="$lit$",De=`lit$${Math.random().toFixed(9).slice(2)}$`,ni="?"+De,sc=`<${ni}>`,yt=document,or=()=>yt.createComment(""),lr=t=>t===null||typeof t!="object"&&typeof t!="function",oi=Array.isArray,La=t=>oi(t)||typeof t?.[Symbol.iterator]=="function",si=`[ 	
\f\r]`,nr=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Na=/-->/g,Ma=/>/g,mt=RegExp(`>|${si}(?:([^\\s"'>=/]+)(${si}*=${si}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),za=/'/g,Va=/"/g,Fa=/^(?:script|style|textarea|title)$/i,li=t=>(e,...r)=>({_$litType$:t,strings:e,values:r}),w=li(1),Ba=li(2),Gd=li(3),J=Symbol.for("lit-noChange"),S=Symbol.for("lit-nothing"),Ua=new WeakMap,gt=yt.createTreeWalker(yt,129);function Ha(t,e){if(!oi(t)||!t.hasOwnProperty("raw"))throw Error("invalid template strings array");return Da!==void 0?Da.createHTML(e):e}var qa=(t,e)=>{let r=t.length-1,s=[],i,a=e===2?"<svg>":e===3?"<math>":"",n=nr;for(let o=0;o<r;o++){let d=t[o],u,c,l=-1,p=0;for(;p<d.length&&(n.lastIndex=p,c=n.exec(d),c!==null);)p=n.lastIndex,n===nr?c[1]==="!--"?n=Na:c[1]!==void 0?n=Ma:c[2]!==void 0?(Fa.test(c[2])&&(i=RegExp("</"+c[2],"g")),n=mt):c[3]!==void 0&&(n=mt):n===mt?c[0]===">"?(n=i??nr,l=-1):c[1]===void 0?l=-2:(l=n.lastIndex-c[2].length,u=c[1],n=c[3]===void 0?mt:c[3]==='"'?Va:za):n===Va||n===za?n=mt:n===Na||n===Ma?n=nr:(n=mt,i=void 0);let h=n===mt&&t[o+1].startsWith("/>")?" ":"";a+=n===nr?d+sc:l>=0?(s.push(u),d.slice(0,l)+ai+d.slice(l)+De+h):d+De+(l===-2?o:h)}return[Ha(t,a+(t[r]||"<?>")+(e===2?"</svg>":e===3?"</math>":"")),s]},cr=class t{constructor({strings:e,_$litType$:r},s){let i;this.parts=[];let a=0,n=0,o=e.length-1,d=this.parts,[u,c]=qa(e,r);if(this.el=t.createElement(u,s),gt.currentNode=this.el.content,r===2||r===3){let l=this.el.content.firstChild;l.replaceWith(...l.childNodes)}for(;(i=gt.nextNode())!==null&&d.length<o;){if(i.nodeType===1){if(i.hasAttributes())for(let l of i.getAttributeNames())if(l.endsWith(ai)){let p=c[n++],h=i.getAttribute(l).split(De),g=/([.?@])?(.*)/.exec(p);d.push({type:1,index:a,name:g[2],strings:h,ctor:g[1]==="."?Kr:g[1]==="?"?Yr:g[1]==="@"?Jr:_t}),i.removeAttribute(l)}else l.startsWith(De)&&(d.push({type:6,index:a}),i.removeAttribute(l));if(Fa.test(i.tagName)){let l=i.textContent.split(De),p=l.length-1;if(p>0){i.textContent=Gr?Gr.emptyScript:"";for(let h=0;h<p;h++)i.append(l[h],or()),gt.nextNode(),d.push({type:2,index:++a});i.append(l[p],or())}}}else if(i.nodeType===8)if(i.data===ni)d.push({type:2,index:a});else{let l=-1;for(;(l=i.data.indexOf(De,l+1))!==-1;)d.push({type:7,index:a}),l+=De.length-1}a++}}static createElement(e,r){let s=yt.createElement("template");return s.innerHTML=e,s}};function vt(t,e,r=t,s){if(e===J)return e;let i=s!==void 0?r._$Co?.[s]:r._$Cl,a=lr(e)?void 0:e._$litDirective$;return i?.constructor!==a&&(i?._$AO?.(!1),a===void 0?i=void 0:(i=new a(t),i._$AT(t,r,s)),s!==void 0?(r._$Co??=[])[s]=i:r._$Cl=i),i!==void 0&&(e=vt(t,i._$AS(t,e.values),i,s)),e}var Xr=class{constructor(e,r){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=r}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){let{el:{content:r},parts:s}=this._$AD,i=(e?.creationScope??yt).importNode(r,!0);gt.currentNode=i;let a=gt.nextNode(),n=0,o=0,d=s[0];for(;d!==void 0;){if(n===d.index){let u;d.type===2?u=new Ut(a,a.nextSibling,this,e):d.type===1?u=new d.ctor(a,d.name,d.strings,this,e):d.type===6&&(u=new Qr(a,this,e)),this._$AV.push(u),d=s[++o]}n!==d?.index&&(a=gt.nextNode(),n++)}return gt.currentNode=yt,i}p(e){let r=0;for(let s of this._$AV)s!==void 0&&(s.strings!==void 0?(s._$AI(e,s,r),r+=s.strings.length-2):s._$AI(e[r])),r++}},Ut=class t{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,r,s,i){this.type=2,this._$AH=S,this._$AN=void 0,this._$AA=e,this._$AB=r,this._$AM=s,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let e=this._$AA.parentNode,r=this._$AM;return r!==void 0&&e?.nodeType===11&&(e=r.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,r=this){e=vt(this,e,r),lr(e)?e===S||e==null||e===""?(this._$AH!==S&&this._$AR(),this._$AH=S):e!==this._$AH&&e!==J&&this._(e):e._$litType$!==void 0?this.$(e):e.nodeType!==void 0?this.T(e):La(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==S&&lr(this._$AH)?this._$AA.nextSibling.data=e:this.T(yt.createTextNode(e)),this._$AH=e}$(e){let{values:r,_$litType$:s}=e,i=typeof s=="number"?this._$AC(e):(s.el===void 0&&(s.el=cr.createElement(Ha(s.h,s.h[0]),this.options)),s);if(this._$AH?._$AD===i)this._$AH.p(r);else{let a=new Xr(i,this),n=a.u(this.options);a.p(r),this.T(n),this._$AH=a}}_$AC(e){let r=Ua.get(e.strings);return r===void 0&&Ua.set(e.strings,r=new cr(e)),r}k(e){oi(this._$AH)||(this._$AH=[],this._$AR());let r=this._$AH,s,i=0;for(let a of e)i===r.length?r.push(s=new t(this.O(or()),this.O(or()),this,this.options)):s=r[i],s._$AI(a),i++;i<r.length&&(this._$AR(s&&s._$AB.nextSibling,i),r.length=i)}_$AR(e=this._$AA.nextSibling,r){for(this._$AP?.(!1,!0,r);e!==this._$AB;){let s=Pa(e).nextSibling;Pa(e).remove(),e=s}}setConnected(e){this._$AM===void 0&&(this._$Cv=e,this._$AP?.(e))}},_t=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,r,s,i,a){this.type=1,this._$AH=S,this._$AN=void 0,this.element=e,this.name=r,this._$AM=i,this.options=a,s.length>2||s[0]!==""||s[1]!==""?(this._$AH=Array(s.length-1).fill(new String),this.strings=s):this._$AH=S}_$AI(e,r=this,s,i){let a=this.strings,n=!1;if(a===void 0)e=vt(this,e,r,0),n=!lr(e)||e!==this._$AH&&e!==J,n&&(this._$AH=e);else{let o=e,d,u;for(e=a[0],d=0;d<a.length-1;d++)u=vt(this,o[s+d],r,d),u===J&&(u=this._$AH[d]),n||=!lr(u)||u!==this._$AH[d],u===S?e=S:e!==S&&(e+=(u??"")+a[d+1]),this._$AH[d]=u}n&&!i&&this.j(e)}j(e){e===S?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}},Kr=class extends _t{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===S?void 0:e}},Yr=class extends _t{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==S)}},Jr=class extends _t{constructor(e,r,s,i,a){super(e,r,s,i,a),this.type=5}_$AI(e,r=this){if((e=vt(this,e,r,0)??S)===J)return;let s=this._$AH,i=e===S&&s!==S||e.capture!==s.capture||e.once!==s.once||e.passive!==s.passive,a=e!==S&&(s===S||i);i&&this.element.removeEventListener(this.name,this,s),a&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}},Qr=class{constructor(e,r,s){this.element=e,this.type=6,this._$AN=void 0,this._$AM=r,this.options=s}get _$AU(){return this._$AM._$AU}_$AI(e){vt(this,e)}},Wa={M:ai,P:De,A:ni,C:1,L:qa,R:Xr,D:La,V:vt,I:Ut,H:_t,N:Yr,U:Jr,B:Kr,F:Qr},ic=ii.litHtmlPolyfillSupport;ic?.(cr,Ut),(ii.litHtmlVersions??=[]).push("3.3.3");var es=(t,e,r)=>{let s=r?.renderBefore??e,i=s._$litPart$;if(i===void 0){let a=r?.renderBefore??null;s._$litPart$=i=new Ut(e.insertBefore(or(),a),a,void 0,r??{})}return i._$AI(t),i};var ci=globalThis,Xe=class extends Pe{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){let r=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=es(r,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return J}};Xe._$litElement$=!0,Xe.finalized=!0,ci.litElementHydrateSupport?.({LitElement:Xe});var ac=ci.litElementPolyfillSupport;ac?.({LitElement:Xe});(ci.litElementVersions??=[]).push("4.2.2");var U=t=>(e,r)=>{r!==void 0?r.addInitializer(()=>{customElements.define(t,e)}):customElements.define(t,e)};var nc={attribute:!0,type:String,converter:ar,reflect:!1,hasChanged:Zr},oc=(t=nc,e,r)=>{let{kind:s,metadata:i}=r,a=globalThis.litPropertyMetadata.get(i);if(a===void 0&&globalThis.litPropertyMetadata.set(i,a=new Map),s==="setter"&&((t=Object.create(t)).wrapped=!0),a.set(r.name,t),s==="accessor"){let{name:n}=r;return{set(o){let d=e.get.call(this);e.set.call(this,o),this.requestUpdate(n,d,t,!0,o)},init(o){return o!==void 0&&this.C(n,void 0,t,o),o}}}if(s==="setter"){let{name:n}=r;return function(o){let d=this[n];e.call(this,o),this.requestUpdate(n,d,t,!0,o)}}throw Error("Unsupported decorator location: "+s)};function A(t){return(e,r)=>typeof r=="object"?oc(t,e,r):((s,i,a)=>{let n=i.hasOwnProperty(a);return i.constructor.createProperty(a,s),n?Object.getOwnPropertyDescriptor(i,a):void 0})(t,e,r)}function ur(t){return A({...t,state:!0,attribute:!1})}var bt=(t,e,r)=>(r.configurable=!0,r.enumerable=!0,Reflect.decorate&&typeof e!="object"&&Object.defineProperty(t,e,r),r);function Za(t,e){return(r,s,i)=>{let a=n=>n.renderRoot?.querySelector(t)??null;if(e){let{get:n,set:o}=typeof s=="object"?r:i??(()=>{let d=Symbol();return{get(){return this[d]},set(u){this[d]=u}}})();return bt(r,s,{get(){let d=n.call(this);return d===void 0&&(d=a(this),(d!==null||this.hasUpdated)&&o.call(this,d)),d}})}return bt(r,s,{get(){return a(this)}})}}var ui=!1,Ga=new G.subtle.Watcher(()=>{ui||(ui=!0,queueMicrotask(()=>{ui=!1;for(let t of Ga.getPending())t.get();Ga.watch()}))}),lc=Symbol("SignalWatcherBrand"),cc=new FinalizationRegistry(t=>{t.unwatch(...G.subtle.introspectSources(t))}),Xa=new WeakMap;function di(t){return t[lc]===!0?(console.warn("SignalWatcher should not be applied to the same class more than once."),t):class extends t{constructor(){super(...arguments),this._$St=new Map,this._$So=new G.State(0),this._$Si=!1}_$Sl(){var e,r;let s=[],i=[];this._$St.forEach((n,o)=>{(n?.beforeUpdate?s:i).push(o)});let a=(e=this.h)===null||e===void 0?void 0:e.getPending().filter(n=>n!==this._$Su&&!this._$St.has(n));s.forEach(n=>n.get()),(r=this._$Su)===null||r===void 0||r.get(),a.forEach(n=>n.get()),i.forEach(n=>n.get())}_$Sv(){this.isUpdatePending||queueMicrotask(()=>{this.isUpdatePending||this._$Sl()})}_$S_(){if(this.h!==void 0)return;this._$Su=new G.Computed(()=>{this._$So.get(),super.performUpdate()});let e=this.h=new G.subtle.Watcher(function(){let r=Xa.get(this);r!==void 0&&(r._$Si===!1&&(new Set(this.getPending()).has(r._$Su)?r.requestUpdate():r._$Sv()),this.watch())});Xa.set(e,this),cc.register(this,e),e.watch(this._$Su),e.watch(...Array.from(this._$St).map(([r])=>r))}_$Sp(){if(this.h===void 0)return;let e=!1;this.h.unwatch(...G.subtle.introspectSources(this.h).filter(r=>{var s;let i=((s=this._$St.get(r))===null||s===void 0?void 0:s.manualDispose)!==!0;return i&&this._$St.delete(r),e||(e=!i),i})),e||(this._$Su=void 0,this.h=void 0,this._$St.clear())}updateEffect(e,r){var s;this._$S_();let i=new G.Computed(()=>{e()});return this.h.watch(i),this._$St.set(i,r),(s=r?.beforeUpdate)!==null&&s!==void 0&&s?G.subtle.untrack(()=>i.get()):this.updateComplete.then(()=>G.subtle.untrack(()=>i.get())),()=>{this._$St.delete(i),this.h.unwatch(i),this.isConnected===!1&&this._$Sp()}}performUpdate(){this.isUpdatePending&&(this._$S_(),this._$Si=!0,this._$So.set(this._$So.get()+1),this._$Si=!1,this._$Sl())}connectedCallback(){super.connectedCallback(),this.requestUpdate()}disconnectedCallback(){super.disconnectedCallback(),queueMicrotask(()=>{this.isConnected===!1&&this._$Sp()})}}}var Te={ATTRIBUTE:1,CHILD:2,PROPERTY:3,BOOLEAN_ATTRIBUTE:4,EVENT:5,ELEMENT:6},ie=t=>(...e)=>({_$litDirective$:t,values:e}),ue=class{constructor(e){}get _$AU(){return this._$AM._$AU}_$AT(e,r,s){this._$Ct=e,this._$AM=r,this._$Ci=s}_$AS(e,r){return this.update(e,r)}update(e,r){return this.render(...r)}};var{I:uc}=Wa,Ka=t=>t,Ja=t=>t===null||typeof t!="object"&&typeof t!="function";var Qa=t=>t.strings===void 0,Ya=()=>document.createComment(""),Lt=(t,e,r)=>{let s=t._$AA.parentNode,i=e===void 0?t._$AB:e._$AA;if(r===void 0){let a=s.insertBefore(Ya(),i),n=s.insertBefore(Ya(),i);r=new uc(a,n,t,t.options)}else{let a=r._$AB.nextSibling,n=r._$AM,o=n!==t;if(o){let d;r._$AQ?.(t),r._$AM=t,r._$AP!==void 0&&(d=t._$AU)!==n._$AU&&r._$AP(d)}if(a!==i||o){let d=r._$AA;for(;d!==a;){let u=Ka(d).nextSibling;Ka(s).insertBefore(d,i),d=u}}}return r},Ke=(t,e,r=t)=>(t._$AI(e,r),t),dc={},en=(t,e=dc)=>t._$AH=e,tn=t=>t._$AH,ts=t=>{t._$AR(),t._$AA.remove()};var dr=(t,e)=>{let r=t._$AN;if(r===void 0)return!1;for(let s of r)s._$AO?.(e,!1),dr(s,e);return!0},rs=t=>{let e,r;do{if((e=t._$AM)===void 0)break;r=e._$AN,r.delete(t),t=e}while(r?.size===0)},rn=t=>{for(let e;e=t._$AM;t=e){let r=e._$AN;if(r===void 0)e._$AN=r=new Set;else if(r.has(t))break;r.add(t),fc(e)}};function hc(t){this._$AN!==void 0?(rs(this),this._$AM=t,rn(this)):this._$AM=t}function pc(t,e=!1,r=0){let s=this._$AH,i=this._$AN;if(i!==void 0&&i.size!==0)if(e)if(Array.isArray(s))for(let a=r;a<s.length;a++)dr(s[a],!1),rs(s[a]);else s!=null&&(dr(s,!1),rs(s));else dr(this,t)}var fc=t=>{t.type==Te.CHILD&&(t._$AP??=pc,t._$AQ??=hc)},Ye=class extends ue{constructor(){super(...arguments),this._$AN=void 0}_$AT(e,r,s){super._$AT(e,r,s),rn(this),this.isConnected=e._$AU}_$AO(e,r=!0){e!==this.isConnected&&(this.isConnected=e,e?this.reconnected?.():this.disconnected?.()),r&&(dr(this,e),rs(this))}setValue(e){if(Qa(this._$Ct))this._$Ct._$AI(e,this);else{let r=[...this._$Ct._$AH];r[this._$Ci]=e,this._$Ct._$AI(r,this,0)}}disconnected(){}reconnected(){}};var hi=!1,pi=new G.subtle.Watcher(async()=>{hi||(hi=!0,queueMicrotask(()=>{hi=!1;for(let t of pi.getPending())t.get();pi.watch()}))}),ss=class extends Ye{_$S_(){var e,r;this._$Sm===void 0&&(this._$Sj=new G.Computed(()=>{var s;let i=(s=this._$SW)===null||s===void 0?void 0:s.get();return this.setValue(i),i}),this._$Sm=(r=(e=this._$Sk)===null||e===void 0?void 0:e.h)!==null&&r!==void 0?r:pi,this._$Sm.watch(this._$Sj),G.subtle.untrack(()=>{var s;return(s=this._$Sj)===null||s===void 0?void 0:s.get()}))}_$Sp(){this._$Sm!==void 0&&(this._$Sm.unwatch(this._$SW),this._$Sm=void 0)}render(e){return G.subtle.untrack(()=>e.get())}update(e,[r]){var s,i;return(s=this._$Sk)!==null&&s!==void 0||(this._$Sk=(i=e.options)===null||i===void 0?void 0:i.host),r!==this._$SW&&this._$SW!==void 0&&this._$Sp(),this._$SW=r,this._$S_(),G.subtle.untrack(()=>this._$SW.get())}disconnected(){this._$Sp()}reconnected(){this._$S_()}},fi=ie(ss);var mi=t=>(e,...r)=>t(e,...r.map(s=>s instanceof G.State||s instanceof G.Computed?fi(s):s)),mc=mi(w),gc=mi(Ba);var ap=G.State,np=G.Computed;var xt=class extends Event{constructor(e,r,s,i){super("context-request",{bubbles:!0,composed:!0}),this.context=e,this.contextTarget=r,this.callback=s,this.subscribe=i??!1}};var Ft=class{constructor(e,r,s,i){if(this.subscribe=!1,this.provided=!1,this.value=void 0,this.t=(a,n)=>{this.unsubscribe&&(this.unsubscribe!==n&&(this.provided=!1,this.unsubscribe()),this.subscribe||this.unsubscribe()),this.value=a,this.host.requestUpdate(),this.provided&&!this.subscribe||(this.provided=!0,this.callback&&this.callback(a,n)),this.unsubscribe=n},this.host=e,r.context!==void 0){let a=r;this.context=a.context,this.callback=a.callback,this.subscribe=a.subscribe??!1}else this.context=r,this.callback=s,this.subscribe=i??!1;this.host.addController(this)}hostConnected(){this.dispatchRequest()}hostDisconnected(){this.unsubscribe&&(this.unsubscribe(),this.unsubscribe=void 0)}dispatchRequest(){this.host.dispatchEvent(new xt(this.context,this.host,this.t,this.subscribe))}};function hr({context:t,subscribe:e}){return(r,s)=>{typeof s=="object"?s.addInitializer((function(){new Ft(this,{context:t,callback:i=>{r.set.call(this,i)},subscribe:e})})):r.constructor.addInitializer((i=>{new Ft(i,{context:t,callback:a=>{i[s]=a},subscribe:e})}))}}function*an(t,e){if(t!==void 0){let r=0;for(let s of t)yield e(s,r++)}}var gi=!1,is=new G.subtle.Watcher(()=>{gi||(gi=!0,queueMicrotask(()=>{gi=!1,vc()}))});function vc(){for(let t of is.getPending())t.get();is.watch()}function nn(t){let e=new G.Computed(()=>t());return is.watch(e),e.get(),()=>{is.unwatch(e)}}var on=Symbol("A2UITheme"),yi=on;var _c=()=>{if(typeof window>"u")return[];try{let t=new CSSStyleSheet;return t.replaceSync(Fs),t}catch(t){throw new Error("Failed to construct structural styles.",{cause:t})}},B=_c();var as=class{constructor(){this.schemas=new Map,this.registry=new Map}register(e,r,s,i){if(!/^[a-zA-Z0-9]+$/.test(e))throw new Error(`[Registry] Invalid typeName '${e}'. Must be alphanumeric.`);this.registry.set(e,r),i&&this.schemas.set(e,i);let a=s||`a2ui-custom-${e.toLowerCase()}`,n=customElements.getName(r);if(n){if(n!==a)throw new Error(`Component ${e} is already registered as ${n}, but requested as ${a}.`);return}customElements.get(a)||customElements.define(a,r)}get(e){return this.registry.get(e)}getInlineCatalog(){let e={};for(let[r,s]of this.schemas)e[r]=s;return{components:e}}},ns=new as;var ne=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},Ne=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},F=(()=>{let t=[U("a2ui-root")],e,r=[],s,i=di(Xe),a=[],n,o=[],d=[],u,c=[],l=[],p,h=[],g=[],m,f=[],v=[],_,b=[],k=[],de,ve=[],Fe=[],Be,He=[],Bt=[],N;var O=class extends i{static{s=this}static{let R=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;n=[A()],u=[A()],p=[hr({context:yi})],m=[A({attribute:!1})],_=[A({attribute:!1})],de=[A()],Be=[A()],N=[A()],Ne(this,null,n,{kind:"accessor",name:"surfaceId",static:!1,private:!1,access:{has:C=>"surfaceId"in C,get:C=>C.surfaceId,set:(C,y)=>{C.surfaceId=y}},metadata:R},o,d),Ne(this,null,u,{kind:"accessor",name:"component",static:!1,private:!1,access:{has:C=>"component"in C,get:C=>C.component,set:(C,y)=>{C.component=y}},metadata:R},c,l),Ne(this,null,p,{kind:"accessor",name:"theme",static:!1,private:!1,access:{has:C=>"theme"in C,get:C=>C.theme,set:(C,y)=>{C.theme=y}},metadata:R},h,g),Ne(this,null,m,{kind:"accessor",name:"childComponents",static:!1,private:!1,access:{has:C=>"childComponents"in C,get:C=>C.childComponents,set:(C,y)=>{C.childComponents=y}},metadata:R},f,v),Ne(this,null,_,{kind:"accessor",name:"processor",static:!1,private:!1,access:{has:C=>"processor"in C,get:C=>C.processor,set:(C,y)=>{C.processor=y}},metadata:R},b,k),Ne(this,null,de,{kind:"accessor",name:"dataContextPath",static:!1,private:!1,access:{has:C=>"dataContextPath"in C,get:C=>C.dataContextPath,set:(C,y)=>{C.dataContextPath=y}},metadata:R},ve,Fe),Ne(this,null,Be,{kind:"accessor",name:"enableCustomElements",static:!1,private:!1,access:{has:C=>"enableCustomElements"in C,get:C=>C.enableCustomElements,set:(C,y)=>{C.enableCustomElements=y}},metadata:R},He,Bt),Ne(this,null,N,{kind:"setter",name:"weight",static:!1,private:!1,access:{has:C=>"weight"in C,set:(C,y)=>{C.weight=y}},metadata:R},null,a),Ne(null,e={value:s},t,{kind:"class",name:s.name,metadata:R},null,r),O=s=e.value,R&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:R})}#e=(ne(this,a),ne(this,o,null));get surfaceId(){return this.#e}set surfaceId(R){this.#e=R}#t=(ne(this,d),ne(this,c,null));get component(){return this.#t}set component(R){this.#t=R}#s=(ne(this,l),ne(this,h,void 0));get theme(){return this.#s}set theme(R){this.#s=R}#r=(ne(this,g),ne(this,f,null));get childComponents(){return this.#r}set childComponents(R){this.#r=R}#i=(ne(this,v),ne(this,b,null));get processor(){return this.#i}set processor(R){this.#i=R}#a=(ne(this,k),ne(this,ve,""));get dataContextPath(){return this.#a}set dataContextPath(R){this.#a=R}#o=(ne(this,Fe),ne(this,He,!1));get enableCustomElements(){return this.#o}set enableCustomElements(R){this.#o=R}set weight(R){this.#l=R,this.style.setProperty("--weight",`${R}`)}get weight(){return this.#l}#l=(ne(this,Bt),1);static{this.styles=[B,z`
      :host {
        display: flex;
        flex-direction: column;
        gap: 8px;
        max-height: 80%;
      }
    `]}#n=null;willUpdate(R){R.has("childComponents")&&(this.#n&&this.#n(),this.#n=nn(()=>{let C=this.childComponents??null,y=this.renderComponentTree(C);es(y,this,{host:this})}))}disconnectedCallback(){super.disconnectedCallback(),this.#n&&this.#n()}renderComponentTree(R){return R?Array.isArray(R)?w` ${an(R,C=>{if(this.enableCustomElements){let K=ns.get(C.type)||customElements.get(C.type);if(K){let X=C,ee=new K;ee.id=X.id,X.slotName&&(ee.slot=X.slotName),ee.component=X,ee.weight=X.weight??"initial",ee.processor=this.processor,ee.surfaceId=this.surfaceId,ee.dataContextPath=X.dataContextPath??"/";for(let[ps,bn]of Object.entries(C.properties))ee[ps]=bn;return w`${ee}`}}switch(C.type){case"List":{let y=C,K=y.properties.children;return w`<a2ui-list
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .direction=${y.properties.direction??"vertical"}
            .processor=${this.processor}
            .surfaceId=${this.surfaceId}
            .childComponents=${K}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-list>`}case"Card":{let y=C,K=y.properties.children;return!K&&y.properties.child&&(K=[y.properties.child]),w`<a2ui-card
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .processor=${this.processor}
            .surfaceId=${this.surfaceId}
            .childComponents=${K}
            .dataContextPath=${y.dataContextPath??""}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-card>`}case"Column":{let y=C;return w`<a2ui-column
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .processor=${this.processor}
            .surfaceId=${this.surfaceId}
            .childComponents=${y.properties.children??null}
            .dataContextPath=${y.dataContextPath??""}
            .alignment=${y.properties.alignment??"stretch"}
            .distribution=${y.properties.distribution??"start"}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-column>`}case"Row":{let y=C;return w`<a2ui-row
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .processor=${this.processor}
            .surfaceId=${this.surfaceId}
            .childComponents=${y.properties.children??null}
            .dataContextPath=${y.dataContextPath??""}
            .alignment=${y.properties.alignment??"stretch"}
            .distribution=${y.properties.distribution??"start"}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-row>`}case"Image":{let y=C;return w`<a2ui-image
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .processor=${this.processor}
            .surfaceId=${this.surfaceId}
            .url=${y.properties.url??null}
            .dataContextPath=${y.dataContextPath??""}
            .usageHint=${y.properties.usageHint}
            .fit=${y.properties.fit}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-image>`}case"Icon":{let y=C;return w`<a2ui-icon
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .processor=${this.processor}
            .surfaceId=${this.surfaceId}
            .name=${y.properties.name??null}
            .dataContextPath=${y.dataContextPath??""}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-icon>`}case"AudioPlayer":{let y=C;return w`<a2ui-audioplayer
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .processor=${this.processor}
            .surfaceId=${this.surfaceId}
            .url=${y.properties.url??null}
            .dataContextPath=${y.dataContextPath??""}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-audioplayer>`}case"Button":{let y=C;return w`<a2ui-button
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .processor=${this.processor}
            .surfaceId=${this.surfaceId}
            .dataContextPath=${y.dataContextPath??""}
            .action=${y.properties.action}
            .childComponents=${[y.properties.child]}
            .primary=${y.properties.primary}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-button>`}case"Text":{let y=C;return w`<a2ui-text
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .model=${this.processor}
            .surfaceId=${this.surfaceId}
            .processor=${this.processor}
            .dataContextPath=${y.dataContextPath}
            .text=${y.properties.text}
            .usageHint=${y.properties.usageHint}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-text>`}case"CheckBox":{let y=C;return w`<a2ui-checkbox
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .processor=${this.processor}
            .surfaceId=${this.surfaceId}
            .dataContextPath=${y.dataContextPath??""}
            .label=${y.properties.label}
            .value=${y.properties.value}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-checkbox>`}case"DateTimeInput":{let y=C;return w`<a2ui-datetimeinput
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .processor=${this.processor}
            .surfaceId=${this.surfaceId}
            .dataContextPath=${y.dataContextPath??""}
            .enableDate=${y.properties.enableDate??!0}
            .enableTime=${y.properties.enableTime??!0}
            .value=${y.properties.value}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-datetimeinput>`}case"Divider":{let y=C;return w`<a2ui-divider
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .processor=${this.processor}
            .surfaceId=${this.surfaceId}
            .dataContextPath=${y.dataContextPath}
            .thickness=${y.properties.thickness}
            .axis=${y.properties.axis}
            .color=${y.properties.color}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-divider>`}case"MultipleChoice":{let y=C;return w`<a2ui-multiplechoice
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .processor=${this.processor}
            .surfaceId=${this.surfaceId}
            .dataContextPath=${y.dataContextPath}
            .options=${y.properties.options}
            .maxAllowedSelections=${y.properties.maxAllowedSelections}
            .selections=${y.properties.selections}
            .variant=${y.properties.variant}
            .filterable=${y.properties.filterable}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-multiplechoice>`}case"Slider":{let y=C;return w`<a2ui-slider
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .processor=${this.processor}
            .surfaceId=${this.surfaceId}
            .dataContextPath=${y.dataContextPath}
            .value=${y.properties.value}
            .minValue=${y.properties.minValue}
            .maxValue=${y.properties.maxValue}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-slider>`}case"TextField":{let y=C;return w`<a2ui-textfield
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .processor=${this.processor}
            .surfaceId=${this.surfaceId}
            .dataContextPath=${y.dataContextPath}
            .label=${y.properties.label}
            .text=${y.properties.text}
            .textFieldType=${y.properties.textFieldType}
            .validationRegexp=${y.properties.validationRegexp}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-textfield>`}case"Video":{let y=C;return w`<a2ui-video
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .processor=${this.processor}
            .surfaceId=${this.surfaceId}
            .dataContextPath=${y.dataContextPath}
            .url=${y.properties.url}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-video>`}case"Tabs":{let y=C,K=[],X=[];if(y.properties.tabItems)for(let ee of y.properties.tabItems)K.push(ee.title),X.push(ee.child);return w`<a2ui-tabs
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .processor=${this.processor}
            .surfaceId=${this.surfaceId}
            .dataContextPath=${y.dataContextPath}
            .titles=${K}
            .childComponents=${X}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-tabs>`}case"Modal":{let y=C,K=[y.properties.entryPointChild,y.properties.contentChild];return y.properties.entryPointChild.slotName="entry",w`<a2ui-modal
            id=${y.id}
            slot=${y.slotName?y.slotName:S}
            .component=${y}
            .weight=${y.weight??"initial"}
            .processor=${this.processor}
            .surfaceId=${this.surfaceId}
            .dataContextPath=${y.dataContextPath}
            .childComponents=${K}
            .enableCustomElements=${this.enableCustomElements}
          ></a2ui-modal>`}default:return this.renderCustomComponent(C)}})}`:S:S}renderCustomComponent(R){if(!this.enableCustomElements)return;let C=R,K=ns.get(R.type)||customElements.get(R.type);if(!K)return w`Unknown element ${R.type}`;let X=new K;X.id=C.id,C.slotName&&(X.slot=C.slotName),X.component=C,X.weight=C.weight??"initial",X.processor=this.processor,X.surfaceId=this.surfaceId,X.dataContextPath=C.dataContextPath??"/";for(let[ee,ps]of Object.entries(R.properties))X[ee]=ps;return w`${X}`}render(){return w`<slot></slot>`}static{ne(s,r)}};return O=s})();function wt(t){if(typeof t!="string")return;let e=t.trim();if(!e||e.startsWith("//")||e.startsWith("\\\\"))return;let r="https://example.invalid/",s;try{s=new URL(e,r)}catch{return}let i=(s.protocol==="http:"||s.protocol==="https:")&&(/^https?:\/\//i.test(e)||s.origin==="https://example.invalid"&&!/^https?:/i.test(e.replace(/[\t\n\r]/g,"")));if(!(s.protocol!=="data:"&&!i))return e}var D=ie(class extends ue{constructor(t){if(super(t),t.type!==Te.ATTRIBUTE||t.name!=="class"||t.strings?.length>2)throw Error("`classMap()` can only be used in the `class` attribute and must be the only part in the attribute.")}render(t){return" "+Object.keys(t).filter(e=>t[e]).join(" ")+" "}update(t,[e]){if(this.st===void 0){this.st=new Set,t.strings!==void 0&&(this.nt=new Set(t.strings.join(" ").split(/\s/).filter(s=>s!=="")));for(let s in e)e[s]&&!this.nt?.has(s)&&this.st.add(s);return this.render(e)}let r=t.element.classList;for(let s of this.st)s in e||(r.remove(s),this.st.delete(s));for(let s in e){let i=!!e[s];i===this.st.has(s)||this.nt?.has(s)||(i?(r.add(s),this.st.add(s)):(r.remove(s),this.st.delete(s)))}return J}});var ln="important",bc=" !"+ln,W=ie(class extends ue{constructor(t){if(super(t),t.type!==Te.ATTRIBUTE||t.name!=="style"||t.strings?.length>2)throw Error("The `styleMap` directive must be used in the `style` attribute and must be the only part in the attribute.")}render(t){return Object.keys(t).reduce((e,r)=>{let s=t[r];return s==null?e:e+`${r=r.includes("-")?r:r.replace(/(?:^(webkit|moz|ms|o)|)(?=[A-Z])/g,"-$&").toLowerCase()}:${s};`},"")}update(t,[e]){let{style:r}=t.element;if(this.ft===void 0)return this.ft=new Set(Object.keys(e)),this.render(e);for(let s of this.ft)e[s]==null&&(this.ft.delete(s),s.includes("-")?r.removeProperty(s):r[s]=null);for(let s in e){let i=e[s];if(i!=null){this.ft.add(s);let a=typeof i=="string"&&i.endsWith(bc);s.includes("-")||a?r.setProperty(s,a?i.slice(0,-11):i,a?ln:""):r[s]=i}}return J}});var cn=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},vi=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},xc=(()=>{let t=[U("a2ui-audioplayer")],e,r=[],s,i=F,a,n=[],o=[];var d=class extends i{static{s=this}static{let u=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[A()],cn(this,null,a,{kind:"accessor",name:"url",static:!1,private:!1,access:{has:c=>"url"in c,get:c=>c.url,set:(c,l)=>{c.url=l}},metadata:u},n,o),cn(null,e={value:s},t,{kind:"class",name:s.name,metadata:u},null,r),d=s=e.value,u&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:u})}#e=vi(this,n,null);get url(){return this.#e}set url(u){this.#e=u}static{this.styles=[B,z`
      * {
        box-sizing: border-box;
      }

      :host {
        display: block;
        flex: var(--weight);
        min-height: 0;
        overflow: auto;
      }

      audio {
        display: block;
        width: 100%;
      }
    `]}#t(){if(!this.url)return S;let u=c=>{let l=wt(c);return l?w`<audio controls src=${l} />`:w`Invalid audio URL`};if(this.url&&typeof this.url=="object"){if("literalString"in this.url)return u(this.url.literalString);if("literal"in this.url)return u(this.url.literal);if(this.url&&"path"in this.url&&this.url.path){if(!this.processor||!this.component)return w`(no processor)`;let c=this.processor.getData(this.component,this.url.path,this.surfaceId??q.DEFAULT_SURFACE_ID);return u(c)}}return w`(empty)`}render(){return w`<section
      class=${D(this.theme.components.AudioPlayer)}
      style=${this.theme.additionalStyles?.AudioPlayer?W(this.theme.additionalStyles?.AudioPlayer):S}
    >
      ${this.#t()}
    </section>`}constructor(){super(...arguments),vi(this,o)}static{vi(s,r)}};return d=s})();var _i=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},pr=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},wc=(()=>{let t=[U("a2ui-button")],e,r=[],s,i=F,a,n=[],o=[],d,u=[],c=[];var l=class extends i{static{s=this}static{let p=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[A()],d=[A()],_i(this,null,a,{kind:"accessor",name:"action",static:!1,private:!1,access:{has:h=>"action"in h,get:h=>h.action,set:(h,g)=>{h.action=g}},metadata:p},n,o),_i(this,null,d,{kind:"accessor",name:"primary",static:!1,private:!1,access:{has:h=>"primary"in h,get:h=>h.primary,set:(h,g)=>{h.primary=g}},metadata:p},u,c),_i(null,e={value:s},t,{kind:"class",name:s.name,metadata:p},null,r),l=s=e.value,p&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:p})}#e=pr(this,n,null);get action(){return this.#e}set action(p){this.#e=p}#t=(pr(this,o),pr(this,u,!1));get primary(){return this.#t}set primary(p){this.#t=p}static{this.styles=[B,z`
      :host {
        display: block;
        flex: var(--weight);
        min-height: 0;
      }
    `]}render(){return w`<button
      class=${D(this.theme.components.Button)}
      style=${this.theme.additionalStyles?.Button?W(this.theme.additionalStyles?.Button):S}
      @click=${()=>{if(!this.action)return;let p=new kr({eventType:"a2ui.action",action:this.action,dataContextPath:this.dataContextPath,sourceComponentId:this.id,sourceComponent:this.component});this.dispatchEvent(p)}}
    >
      <slot></slot>
    </button>`}constructor(){super(...arguments),pr(this,c)}static{pr(s,r)}};return l=s})();var $c=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},Sc=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},Cc=(()=>{let t=[U("a2ui-card")],e,r=[],s,i=F;var a=class extends i{static{s=this}static{let n=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;$c(null,e={value:s},t,{kind:"class",name:s.name,metadata:n},null,r),a=s=e.value,n&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:n})}static{this.styles=[B,z`
      * {
        box-sizing: border-box;
      }

      :host {
        display: block;
        flex: var(--weight);
        min-height: 0;
        overflow: auto;
      }

      section {
        height: 100%;
        width: 100%;
        min-height: 0;
        overflow: auto;

        ::slotted(*) {
          height: 100%;
          width: 100%;
        }
      }
    `]}render(){return w` <section
      class=${D(this.theme.components.Card)}
      style=${this.theme.additionalStyles?.Card?W(this.theme.additionalStyles?.Card):S}
    >
      <slot></slot>
    </section>`}static{Sc(s,r)}};return a=s})();function xe(t,e,r,s){if(t!==null&&typeof t=="object"){if("literalString"in t)return t.literalString??"";if("literal"in t&&t.literal!==void 0)return t.literal??"";if(t&&"path"in t&&t.path){if(!r||!e)return"(no model)";let i=r.getData(e,t.path,s??q.DEFAULT_SURFACE_ID);return i===null||typeof i!="string"?"":i}}return""}function un(t,e,r,s){if(t!==null&&typeof t=="object"){if("literalNumber"in t)return t.literalNumber??0;if("literal"in t&&t.literal!==void 0)return t.literal??0;if(t&&"path"in t&&t.path){if(!r||!e)return-1;let i=r.getData(e,t.path,s??q.DEFAULT_SURFACE_ID);return typeof i=="string"&&(i=Number.parseInt(i,10),Number.isNaN(i)&&(i=null)),i===null||typeof i!="number"?-1:i}}return 0}var bi=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},fr=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},Tc=(()=>{let t=[U("a2ui-checkbox")],e,r=[],s,i=F,a,n=[],o=[],d,u=[],c=[];var l=class extends i{static{s=this}static{let p=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[A()],d=[A()],bi(this,null,a,{kind:"accessor",name:"value",static:!1,private:!1,access:{has:h=>"value"in h,get:h=>h.value,set:(h,g)=>{h.value=g}},metadata:p},n,o),bi(this,null,d,{kind:"accessor",name:"label",static:!1,private:!1,access:{has:h=>"label"in h,get:h=>h.label,set:(h,g)=>{h.label=g}},metadata:p},u,c),bi(null,e={value:s},t,{kind:"class",name:s.name,metadata:p},null,r),l=s=e.value,p&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:p})}#e=fr(this,n,null);get value(){return this.#e}set value(p){this.#e=p}#t=(fr(this,o),fr(this,u,null));get label(){return this.#t}set label(p){this.#t=p}static{this.styles=[B,z`
      * {
        box-sizing: border-box;
      }

      :host {
        display: block;
        flex: var(--weight);
        min-height: 0;
        overflow: auto;
      }

      input {
        display: block;
        width: 100%;
      }

      .description {
        font-size: 14px;
        margin-bottom: 4px;
      }
    `]}#s(p){!this.value||!this.processor||"path"in this.value&&this.value.path&&this.processor.setData(this.component,this.value.path,p,this.surfaceId??q.DEFAULT_SURFACE_ID)}#r(p){return w` <section
      class=${D(this.theme.components.CheckBox.container)}
      style=${this.theme.additionalStyles?.CheckBox?W(this.theme.additionalStyles?.CheckBox):S}
    >
      <input
        class=${D(this.theme.components.CheckBox.element)}
        autocomplete="off"
        @input=${h=>{h.target instanceof HTMLInputElement&&this.#s(h.target.checked)}}
        id="data"
        type="checkbox"
        .checked=${p}
      />
      <label class=${D(this.theme.components.CheckBox.label)} for="data"
        >${xe(this.label,this.component,this.processor,this.surfaceId)}</label
      >
    </section>`}render(){if(this.value&&typeof this.value=="object"){if("literalBoolean"in this.value&&this.value.literalBoolean)return this.#r(this.value.literalBoolean);if("literal"in this.value&&this.value.literal!==void 0)return this.#r(this.value.literal);if(this.value&&"path"in this.value&&this.value.path){if(!this.processor||!this.component)return w`(no model)`;let p=this.processor.getData(this.component,this.value.path,this.surfaceId??q.DEFAULT_SURFACE_ID);return p===null?w`Invalid label`:typeof p!="boolean"?w`Invalid label`:this.#r(p)}}return S}constructor(){super(...arguments),fr(this,c)}static{fr(s,r)}};return l=s})();var xi=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},mr=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},Ec=(()=>{let t=[U("a2ui-column")],e,r=[],s,i=F,a,n=[],o=[],d,u=[],c=[];var l=class extends i{static{s=this}static{let p=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[A({reflect:!0,type:String})],d=[A({reflect:!0,type:String})],xi(this,null,a,{kind:"accessor",name:"alignment",static:!1,private:!1,access:{has:h=>"alignment"in h,get:h=>h.alignment,set:(h,g)=>{h.alignment=g}},metadata:p},n,o),xi(this,null,d,{kind:"accessor",name:"distribution",static:!1,private:!1,access:{has:h=>"distribution"in h,get:h=>h.distribution,set:(h,g)=>{h.distribution=g}},metadata:p},u,c),xi(null,e={value:s},t,{kind:"class",name:s.name,metadata:p},null,r),l=s=e.value,p&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:p})}#e=mr(this,n,"stretch");get alignment(){return this.#e}set alignment(p){this.#e=p}#t=(mr(this,o),mr(this,u,"start"));get distribution(){return this.#t}set distribution(p){this.#t=p}static{this.styles=[B,z`
      * {
        box-sizing: border-box;
      }

      :host {
        display: flex;
        flex: var(--weight);
      }

      section {
        display: flex;
        flex-direction: column;
        min-width: 100%;
        height: 100%;
      }

      :host([alignment='start']) section {
        align-items: start;
      }

      :host([alignment='center']) section {
        align-items: center;
      }

      :host([alignment='end']) section {
        align-items: end;
      }

      :host([alignment='stretch']) section {
        align-items: stretch;
      }

      :host([distribution='start']) section {
        justify-content: start;
      }

      :host([distribution='center']) section {
        justify-content: center;
      }

      :host([distribution='end']) section {
        justify-content: end;
      }

      :host([distribution='spaceBetween']) section {
        justify-content: space-between;
      }

      :host([distribution='spaceAround']) section {
        justify-content: space-around;
      }

      :host([distribution='spaceEvenly']) section {
        justify-content: space-evenly;
      }
    `]}render(){return w`<section
      class=${D(this.theme.components.Column)}
      style=${this.theme.additionalStyles?.Column?W(this.theme.additionalStyles?.Column):S}
    >
      <slot></slot>
    </section>`}constructor(){super(...arguments),mr(this,c)}static{mr(s,r)}};return l=s})();var gr=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},Me=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},wi=(()=>{let t=[U("a2ui-datetimeinput")],e,r=[],s,i=F,a,n=[],o=[],d,u=[],c=[],l,p=[],h=[],g,m=[],f=[];var v=class extends i{static{s=this}static{let _=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[A()],d=[A()],l=[A({reflect:!1,type:Boolean})],g=[A({reflect:!1,type:Boolean})],gr(this,null,a,{kind:"accessor",name:"value",static:!1,private:!1,access:{has:b=>"value"in b,get:b=>b.value,set:(b,k)=>{b.value=k}},metadata:_},n,o),gr(this,null,d,{kind:"accessor",name:"label",static:!1,private:!1,access:{has:b=>"label"in b,get:b=>b.label,set:(b,k)=>{b.label=k}},metadata:_},u,c),gr(this,null,l,{kind:"accessor",name:"enableDate",static:!1,private:!1,access:{has:b=>"enableDate"in b,get:b=>b.enableDate,set:(b,k)=>{b.enableDate=k}},metadata:_},p,h),gr(this,null,g,{kind:"accessor",name:"enableTime",static:!1,private:!1,access:{has:b=>"enableTime"in b,get:b=>b.enableTime,set:(b,k)=>{b.enableTime=k}},metadata:_},m,f),gr(null,e={value:s},t,{kind:"class",name:s.name,metadata:_},null,r),v=s=e.value,_&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:_})}#e=Me(this,n,null);get value(){return this.#e}set value(_){this.#e=_}#t=(Me(this,o),Me(this,u,null));get label(){return this.#t}set label(_){this.#t=_}#s=(Me(this,c),Me(this,p,!0));get enableDate(){return this.#s}set enableDate(_){this.#s=_}#r=(Me(this,h),Me(this,m,!0));get enableTime(){return this.#r}set enableTime(_){this.#r=_}static{this.styles=[B,z`
      * {
        box-sizing: border-box;
      }

      :host {
        display: block;
        flex: var(--weight);
        min-height: 0;
        overflow: auto;
      }

      input {
        display: block;
        border-radius: 8px;
        padding: 8px;
        border: 1px solid #ccc;
        width: 100%;
        color: #333;
      }

      input::-webkit-datetime-edit,
      input::-webkit-datetime-edit-fields-wrapper {
        color: #333;
      }
    `]}#i(_){!this.value||!this.processor||"path"in this.value&&this.value.path&&this.processor.setData(this.component,this.value.path,_,this.surfaceId??q.DEFAULT_SURFACE_ID)}#a(_){return w`<section class=${D(this.theme.components.DateTimeInput.container)}>
      <label for="data" class=${D(this.theme.components.DateTimeInput.label)}
        >${this.#c()}</label
      >
      <input
        autocomplete="off"
        class=${D(this.theme.components.DateTimeInput.element)}
        style=${this.theme.additionalStyles?.DateTimeInput?W(this.theme.additionalStyles?.DateTimeInput):S}
        @input=${b=>{b.target instanceof HTMLInputElement&&this.#i(b.target.value)}}
        id="data"
        name="data"
        .value=${this.#l(_)}
        .placeholder=${this.#c()}
        .type=${this.#o()}
      />
    </section>`}#o(){return this.enableDate&&this.enableTime?"datetime-local":this.enableDate?"date":this.enableTime?"time":"datetime-local"}#l(_){let b=this.#o(),k=_?new Date(_):null;if(!k||isNaN(k.getTime()))return"";let de=this.#n(k.getFullYear()),ve=this.#n(k.getMonth()+1),Fe=this.#n(k.getDate()),Be=this.#n(k.getHours()),He=this.#n(k.getMinutes());return b==="date"?`${de}-${ve}-${Fe}`:b==="time"?`${Be}:${He}`:`${de}-${ve}-${Fe}T${Be}:${He}`}#n(_){return _.toString().padStart(2,"0")}#c(){let _=this.#o();return _==="date"?"Date":_==="time"?"Time":"Date & Time"}render(){if(this.value&&typeof this.value=="object"){if("literalString"in this.value&&this.value.literalString)return this.#a(this.value.literalString);if("literal"in this.value&&this.value.literal!==void 0)return this.#a(this.value.literal);if(this.value&&"path"in this.value&&this.value.path){if(!this.processor||!this.component)return w`(no model)`;let _=this.processor.getData(this.component,this.value.path,this.surfaceId??q.DEFAULT_SURFACE_ID);return typeof _!="string"?w`(invalid)`:this.#a(_)}}return S}constructor(){super(...arguments),Me(this,f)}static{Me(s,r)}};return v=s})();var os=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},$t=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},Ac=(()=>{let t=[U("a2ui-divider")],e,r=[],s,i=F,a,n=[],o=[],d,u=[],c=[],l,p=[],h=[];var g=class extends i{static{s=this}static{let m=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[A()],d=[A()],l=[A({type:Number})],os(this,null,a,{kind:"accessor",name:"axis",static:!1,private:!1,access:{has:f=>"axis"in f,get:f=>f.axis,set:(f,v)=>{f.axis=v}},metadata:m},n,o),os(this,null,d,{kind:"accessor",name:"color",static:!1,private:!1,access:{has:f=>"color"in f,get:f=>f.color,set:(f,v)=>{f.color=v}},metadata:m},u,c),os(this,null,l,{kind:"accessor",name:"thickness",static:!1,private:!1,access:{has:f=>"thickness"in f,get:f=>f.thickness,set:(f,v)=>{f.thickness=v}},metadata:m},p,h),os(null,e={value:s},t,{kind:"class",name:s.name,metadata:m},null,r),g=s=e.value,m&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:m})}#e=$t(this,n,"horizontal");get axis(){return this.#e}set axis(m){this.#e=m}#t=($t(this,o),$t(this,u,null));get color(){return this.#t}set color(m){this.#t=m}#s=($t(this,c),$t(this,p,null));get thickness(){return this.#s}set thickness(m){this.#s=m}static{this.styles=[B,z`
      :host {
        display: block;
        min-height: 0;
        overflow: auto;
        align-self: stretch;
      }

      hr,
      .vertical-divider {
        background: #ccc;
        border: none;
      }

      hr {
        height: 1px;
      }

      .vertical-divider {
        width: 1px;
        height: 100%;
      }
    `]}render(){let f={...typeof this.theme?.components?.Divider=="string"?{[this.theme.components.Divider]:!0}:this.theme?.components?.Divider,vertical:this.axis==="vertical",horizontal:this.axis!=="vertical"},v={};this.color&&(v["background-color"]=this.color),this.thickness!==null&&this.thickness!==void 0&&(this.axis==="vertical"?v.width=`${this.thickness}px`:v.height=`${this.thickness}px`);let _={...this.theme?.additionalStyles?.Divider,...v};return this.axis==="vertical"?w`<div
          class=${D({...f,"vertical-divider":!0})}
          style=${W(_)}
        ></div>`:w`<hr class=${D(f)} style=${W(_)} />`}constructor(){super(...arguments),$t(this,h)}static{$t(s,r)}};return g=s})();var dn=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},$i=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},Ic=(()=>{let t=[U("a2ui-icon")],e,r=[],s,i=F,a,n=[],o=[];var d=class extends i{static{s=this}static{let u=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[A()],dn(this,null,a,{kind:"accessor",name:"name",static:!1,private:!1,access:{has:c=>"name"in c,get:c=>c.name,set:(c,l)=>{c.name=l}},metadata:u},n,o),dn(null,e={value:s},t,{kind:"class",name:s.name,metadata:u},null,r),d=s=e.value,u&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:u})}#e=$i(this,n,null);get name(){return this.#e}set name(u){this.#e=u}static{this.styles=[B,z`
      * {
        box-sizing: border-box;
      }

      :host {
        display: block;
        flex: var(--weight);
        min-height: 0;
      }

      .g-icon {
        font-family: 'Material Symbols Outlined';
        font-weight: normal;
        font-style: normal;
        font-size: 24px;
        display: inline-block;
        line-height: 1;
        text-transform: none;
        letter-spacing: normal;
        word-wrap: normal;
        white-space: nowrap;
        direction: ltr;
        -webkit-font-smoothing: antialiased;
        text-rendering: optimizeLegibility;
        -moz-osx-font-smoothing: grayscale;
        font-feature-settings: 'liga';
      }
    `]}#t(){if(!this.name)return S;let u=c=>(c=c.replace(/([A-Z])/gm,"_$1").toLocaleLowerCase(),w`<span class="g-icon">${c}</span>`);if(this.name&&typeof this.name=="object"){if("literalString"in this.name){let c=this.name.literalString??"";return u(c)}else if("literal"in this.name){let c=this.name.literal??"";return u(c)}else if(this.name&&"path"in this.name&&this.name.path){if(!this.processor||!this.component)return w`(no model)`;let c=this.processor.getData(this.component,this.name.path,this.surfaceId??q.DEFAULT_SURFACE_ID);return c?typeof c!="string"?w`Invalid icon name`:u(c):w`Invalid icon name`}}return w`(empty)`}render(){return w`<section
      class=${D(this.theme.components.Icon)}
      style=${this.theme.additionalStyles?.Icon?W(this.theme.additionalStyles?.Icon):S}
    >
      ${this.#t()}
    </section>`}constructor(){super(...arguments),$i(this,o)}static{$i(s,r)}};return d=s})();var yr=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},ze=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},Oc=(()=>{let t=[U("a2ui-image")],e,r=[],s,i=F,a,n=[],o=[],d,u=[],c=[],l,p=[],h=[],g,m=[],f=[];var v=class extends i{static{s=this}static{let _=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[A()],d=[A()],l=[A()],g=[A()],yr(this,null,a,{kind:"accessor",name:"url",static:!1,private:!1,access:{has:b=>"url"in b,get:b=>b.url,set:(b,k)=>{b.url=k}},metadata:_},n,o),yr(this,null,d,{kind:"accessor",name:"altText",static:!1,private:!1,access:{has:b=>"altText"in b,get:b=>b.altText,set:(b,k)=>{b.altText=k}},metadata:_},u,c),yr(this,null,l,{kind:"accessor",name:"usageHint",static:!1,private:!1,access:{has:b=>"usageHint"in b,get:b=>b.usageHint,set:(b,k)=>{b.usageHint=k}},metadata:_},p,h),yr(this,null,g,{kind:"accessor",name:"fit",static:!1,private:!1,access:{has:b=>"fit"in b,get:b=>b.fit,set:(b,k)=>{b.fit=k}},metadata:_},m,f),yr(null,e={value:s},t,{kind:"class",name:s.name,metadata:_},null,r),v=s=e.value,_&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:_})}#e=ze(this,n,null);get url(){return this.#e}set url(_){this.#e=_}#t=(ze(this,o),ze(this,u,null));get altText(){return this.#t}set altText(_){this.#t=_}#s=(ze(this,c),ze(this,p,null));get usageHint(){return this.#s}set usageHint(_){this.#s=_}#r=(ze(this,h),ze(this,m,null));get fit(){return this.#r}set fit(_){this.#r=_}static{this.styles=[B,z`
      * {
        box-sizing: border-box;
      }

      :host {
        display: block;
        flex: var(--weight);
        min-height: 0;
        overflow: auto;
      }

      img {
        display: block;
        width: 100%;
        height: 100%;
        object-fit: var(--object-fit, fill);
      }
    `]}#i(){if(!this.url)return S;let _=b=>{let k=wt(b);if(!k)return w`Invalid image URL`;let de="";if(this.altText&&typeof this.altText=="object"){if("literalString"in this.altText)de=this.altText.literalString??"";else if("literal"in this.altText)de=this.altText.literal??"";else if("path"in this.altText&&this.altText.path&&this.processor&&this.component){let ve=this.processor.getData(this.component,this.altText.path,this.surfaceId??q.DEFAULT_SURFACE_ID);typeof ve=="string"&&(de=ve)}}return w`<img src=${k} alt=${de} />`};if(this.url&&typeof this.url=="object"){if("literalString"in this.url)return _(this.url.literalString);if("literal"in this.url)return _(this.url.literal);if(this.url&&"path"in this.url&&this.url.path){if(!this.processor||!this.component)return w`(no model)`;let b=this.processor.getData(this.component,this.url.path,this.surfaceId??q.DEFAULT_SURFACE_ID);return _(b)}}return w`(empty)`}render(){let _=ke.merge(this.theme.components.Image.all,this.usageHint?this.theme.components.Image[this.usageHint]:{});return w`<section
      class=${D(_)}
      style=${W({...this.theme.additionalStyles?.Image??{},"--object-fit":this.fit??"fill"})}
    >
      ${this.#i()}
    </section>`}constructor(){super(...arguments),ze(this,f)}static{ze(s,r)}};return v=s})();var hn=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},Si=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},jc=(()=>{let t=[U("a2ui-list")],e,r=[],s,i=F,a,n=[],o=[];var d=class extends i{static{s=this}static{let u=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[A({reflect:!0,type:String})],hn(this,null,a,{kind:"accessor",name:"direction",static:!1,private:!1,access:{has:c=>"direction"in c,get:c=>c.direction,set:(c,l)=>{c.direction=l}},metadata:u},n,o),hn(null,e={value:s},t,{kind:"class",name:s.name,metadata:u},null,r),d=s=e.value,u&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:u})}#e=Si(this,n,"vertical");get direction(){return this.#e}set direction(u){this.#e=u}static{this.styles=[B,z`
      * {
        box-sizing: border-box;
      }

      :host {
        display: block;
        flex: var(--weight);
        min-height: 0;
        overflow: auto;
      }

      :host([direction='vertical']) section {
        display: grid;
      }

      :host([direction='horizontal']) section {
        display: flex;
        max-width: 100%;
        overflow-x: scroll;
        overflow-y: hidden;
        scrollbar-width: none;

        > ::slotted(*) {
          flex: 1 0 fit-content;
          max-width: min(80%, 400px);
        }
      }
    `]}render(){return w`<section
      class=${D(this.theme.components.List)}
      style=${this.theme.additionalStyles?.List?W(this.theme.additionalStyles?.List):S}
    >
      <slot></slot>
    </section>`}constructor(){super(...arguments),Si(this,o)}static{Si(s,r)}};return d=s})();var Je=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},oe=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},Pc=(()=>{let t=[U("a2ui-multiplechoice")],e,r=[],s,i=F,a,n=[],o=[],d,u=[],c=[],l,p=[],h=[],g,m=[],f=[],v,_=[],b=[],k,de=[],ve=[],Fe,Be=[],He=[];var Bt=class extends i{static{s=this}static{let N=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[A()],d=[A()],l=[A()],g=[A()],v=[A({type:Boolean})],k=[ur()],Fe=[ur()],Je(this,null,a,{kind:"accessor",name:"description",static:!1,private:!1,access:{has:O=>"description"in O,get:O=>O.description,set:(O,R)=>{O.description=R}},metadata:N},n,o),Je(this,null,d,{kind:"accessor",name:"options",static:!1,private:!1,access:{has:O=>"options"in O,get:O=>O.options,set:(O,R)=>{O.options=R}},metadata:N},u,c),Je(this,null,l,{kind:"accessor",name:"selections",static:!1,private:!1,access:{has:O=>"selections"in O,get:O=>O.selections,set:(O,R)=>{O.selections=R}},metadata:N},p,h),Je(this,null,g,{kind:"accessor",name:"variant",static:!1,private:!1,access:{has:O=>"variant"in O,get:O=>O.variant,set:(O,R)=>{O.variant=R}},metadata:N},m,f),Je(this,null,v,{kind:"accessor",name:"filterable",static:!1,private:!1,access:{has:O=>"filterable"in O,get:O=>O.filterable,set:(O,R)=>{O.filterable=R}},metadata:N},_,b),Je(this,null,k,{kind:"accessor",name:"isOpen",static:!1,private:!1,access:{has:O=>"isOpen"in O,get:O=>O.isOpen,set:(O,R)=>{O.isOpen=R}},metadata:N},de,ve),Je(this,null,Fe,{kind:"accessor",name:"filterText",static:!1,private:!1,access:{has:O=>"filterText"in O,get:O=>O.filterText,set:(O,R)=>{O.filterText=R}},metadata:N},Be,He),Je(null,e={value:s},t,{kind:"class",name:s.name,metadata:N},null,r),Bt=s=e.value,N&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:N})}#e=oe(this,n,null);get description(){return this.#e}set description(N){this.#e=N}#t=(oe(this,o),oe(this,u,[]));get options(){return this.#t}set options(N){this.#t=N}#s=(oe(this,c),oe(this,p,[]));get selections(){return this.#s}set selections(N){this.#s=N}#r=(oe(this,h),oe(this,m,"checkbox"));get variant(){return this.#r}set variant(N){this.#r=N}#i=(oe(this,f),oe(this,_,!1));get filterable(){return this.#i}set filterable(N){this.#i=N}#a=(oe(this,b),oe(this,de,!1));get isOpen(){return this.#a}set isOpen(N){this.#a=N}#o=(oe(this,ve),oe(this,Be,""));get filterText(){return this.#o}set filterText(N){this.#o=N}static{this.styles=[B,z`
      * {
        box-sizing: border-box;
      }

      :host {
        display: block;
        flex: var(--weight);
        min-height: 0;
        position: relative;
        font-family: 'Google Sans', 'Roboto', sans-serif;
      }

      .container {
        display: flex;
        flex-direction: column;
        gap: 4px;
        position: relative;
      }

      /* Header / Trigger */
      .dropdown-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 16px;
        background: var(--md-sys-color-surface);
        border: 1px solid var(--md-sys-color-outline-variant);
        border-radius: 8px;
        cursor: pointer;
        user-select: none;
        transition: background-color 0.2s;
        box-shadow: var(--md-sys-elevation-level1);
      }

      .dropdown-header:hover {
        background: var(--md-sys-color-surface-container-low);
      }

      .header-text {
        font-size: 1rem;
        color: var(--md-sys-color-on-surface);
        font-weight: 400;
      }

      .chevron {
        color: var(--md-sys-color-primary);
        font-size: 1.2rem;
        transition: transform 0.2s ease;
      }

      .chevron.open {
        transform: rotate(180deg);
      }

      /* Dropdown Wrapper */
      .dropdown-wrapper {
        background: var(--md-sys-color-surface);
        border: 1px solid var(--md-sys-color-outline-variant);
        border-radius: 8px;
        box-shadow: var(--md-sys-elevation-level2);
        padding: 0;
        display: none;
        flex-direction: column;
        margin-top: 4px;
        max-height: 300px;
        transition: opacity 0.2s ease-out;
        overflow: hidden; /* contain children */
      }

      .dropdown-wrapper.open {
        display: flex;
        border: 1px solid var(--md-sys-color-outline-variant);
      }

      /* Scrollable Area for Options */
      .options-scroll-container {
        overflow-y: auto;
        flex: 1; /* take remaining height */
        display: flex;
        flex-direction: column;
      }

      /* Filter Input */
      .filter-container {
        padding: 8px;
        border-bottom: 1px solid var(--md-sys-color-outline-variant);
        background: var(--md-sys-color-surface);
        z-index: 1; /* ensure top of stack */
        flex-shrink: 0; /* don't shrink */
      }

      .filter-input {
        width: 100%;
        padding: 8px 12px;
        border: 1px solid var(--md-sys-color-outline);
        border-radius: 4px;
        font-family: inherit;
        font-size: 0.9rem;
        background: var(--md-sys-color-surface-container-low);
        color: var(--md-sys-color-on-surface);
      }

      .filter-input:focus {
        outline: none;
        border-color: var(--md-sys-color-primary);
      }

      /* Option Item (Checkbox style) */
      .option-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px 16px;
        cursor: pointer;
        color: var(--md-sys-color-on-surface);
        font-size: 0.95rem;
        transition: background-color 0.1s;
      }

      .option-item:hover {
        background: var(--md-sys-color-surface-container-highest);
      }

      /* Custom Checkbox */
      .checkbox {
        width: 18px;
        height: 18px;
        border: 2px solid var(--md-sys-color-outline);
        border-radius: 2px;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s;
        flex-shrink: 0;
      }

      .option-item.selected .checkbox {
        background: var(--md-sys-color-primary);
        border-color: var(--md-sys-color-primary);
      }

      .checkbox-icon {
        color: var(--md-sys-color-on-primary);
        font-size: 14px;
        font-weight: bold;
        opacity: 0;
        transform: scale(0.5);
        transition: all 0.2s;
      }

      .option-item.selected .checkbox-icon {
        opacity: 1;
        transform: scale(1);
      }

      /* Chips Layout */
      .chips-container {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        padding: 4px 0;
      }

      .chip {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 16px;
        border: 1px solid var(--md-sys-color-outline);
        border-radius: 16px;
        cursor: pointer;
        user-select: none;
        background: var(--md-sys-color-surface);
        color: var(--md-sys-color-on-surface);
        transition: all 0.2s ease;
        font-size: 0.9rem;
      }

      .chip:hover {
        background: var(--md-sys-color-surface-container-high);
      }

      .chip.selected {
        background: var(--md-sys-color-secondary-container);
        color: var(--md-sys-color-on-secondary-container);
        border-color: var(--md-sys-color-secondary-container);
      }

      .chip.selected:hover {
        background: var(--md-sys-color-secondary-container-high);
      }

      .chip-icon {
        display: none;
        width: 18px;
        height: 18px;
      }

      .chip.selected .chip-icon {
        display: block;
        fill: currentColor;
      }

      @keyframes fadeIn {
        from {
          opacity: 0;
          transform: translateY(-8px);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }
    `]}#l(N){!this.selections||!this.processor||"path"in this.selections&&this.selections.path&&this.processor.setData(this.component,this.selections.path,N,this.surfaceId??q.DEFAULT_SURFACE_ID)}getCurrentSelections(){if(Array.isArray(this.selections))return this.selections;if(!this.processor||!this.component)return[];let N=this.processor.getData(this.component,this.selections.path,this.surfaceId??q.DEFAULT_SURFACE_ID);return Array.isArray(N)?N:[]}toggleSelection(N){let O=this.getCurrentSelections();O.includes(N)?this.#l(O.filter(R=>R!==N)):this.#l([...O,N]),this.requestUpdate()}#n(){return w`
      <svg class="chip-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960">
        <path d="M382-240 154-468l57-57 171 171 367-367 57 57-424 424Z" />
      </svg>
    `}#c(){return w`
      <div class="filter-container">
        <input
          type="text"
          class="filter-input"
          placeholder="Filter options..."
          .value=${this.filterText}
          @input=${N=>{let O=N.target;this.filterText=O.value}}
          @click=${N=>N.stopPropagation()}
        />
      </div>
    `}render(){let N=this.getCurrentSelections(),O=this.options.filter(y=>this.filterText?xe(y.label,this.component,this.processor,this.surfaceId).toLowerCase().includes(this.filterText.toLowerCase()):!0);if(this.variant==="chips")return w`
        <div class="container">
          ${this.description?w`<div class="header-text" style="margin-bottom: 8px;">${this.description}</div>`:S}
          ${this.filterable?this.#c():S}
          <div class="chips-container">
            ${O.map(y=>{let K=xe(y.label,this.component,this.processor,this.surfaceId),X=N.includes(y.value);return w`
                <div
                  class="chip ${X?"selected":""}"
                  @click=${ee=>{ee.stopPropagation(),this.toggleSelection(y.value)}}
                >
                  ${X?this.#n():S}
                  <span>${K}</span>
                </div>
              `})}
          </div>
          ${O.length===0?w`<div
                style="padding: 8px; font-style: italic; color: var(--md-sys-color-outline);"
              >
                No options found
              </div>`:S}
        </div>
      `;let R=N.length,C=R>0?`${R} Selected`:this.description??"Select items";return w`
      <div class="container">
        <div class="dropdown-header" @click=${()=>this.isOpen=!this.isOpen}>
          <span class="header-text">${C}</span>
          <span class="chevron ${this.isOpen?"open":""}">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              height="24"
              viewBox="0 -960 960 960"
              width="24"
              fill="currentColor"
            >
              <path d="M480-345 240-585l56-56 184 184 184-184 56 56-240 240Z" />
            </svg>
          </span>
        </div>

        <div class="dropdown-wrapper ${this.isOpen?"open":""}">
          ${this.filterable?this.#c():S}
          <div class="options-scroll-container">
            ${O.map(y=>{let K=xe(y.label,this.component,this.processor,this.surfaceId),X=N.includes(y.value);return w`
                <div
                  class="option-item ${X?"selected":""}"
                  @click=${ee=>{ee.stopPropagation(),this.toggleSelection(y.value)}}
                >
                  <div class="checkbox">
                    <span class="checkbox-icon">✓</span>
                  </div>
                  <span>${K}</span>
                </div>
              `})}
            ${O.length===0?w`<div
                  style="padding: 16px; text-align: center; color: var(--md-sys-color-outline);"
                >
                  No options found
                </div>`:S}
          </div>
        </div>
      </div>
    `}constructor(){super(...arguments),oe(this,He)}static{oe(s,r)}};return Bt=s})();var Ci=new WeakMap,pn=ie(class extends Ye{render(t){return S}update(t,[e]){let r=e!==this.G;return r&&this.rt(void 0),(r||this.lt!==this.ct)&&(this.G=e,this.ht=t.options?.host,this.rt(this.ct=t.element)),S}rt(t){if(this.G!==void 0)if(this.isConnected||(t=void 0),typeof this.G=="function"){let e=this.ht??globalThis,r=Ci.get(e);r===void 0&&(r=new WeakMap,Ci.set(e,r)),r.get(this.G)!==void 0&&this.G.call(this.ht,void 0),r.set(this.G,t),t!==void 0&&this.G.call(this.ht,t)}else this.G.value=t}get lt(){return typeof this.G=="function"?Ci.get(this.ht??globalThis)?.get(this.G):this.G?.value}disconnected(){this.lt===this.ct&&this.rt(void 0)}reconnected(){this.rt(this.ct)}});var ki=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},vr=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},ls=function(t,e,r){return typeof e=="symbol"&&(e=e.description?"[".concat(e.description,"]"):""),Object.defineProperty(t,"name",{configurable:!0,value:r?"".concat(r," ",e):e})},Dc=(()=>{let t=[U("a2ui-modal")],e,r=[],s,i=F,a,n=[],o=[],d,u,c=[],l=[],p;var h=class extends i{static{s=this}static{let g=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[ur()],u=[Za("dialog")],ki(this,d={get:ls(function(){return this.#e},"#showModal","get"),set:ls(function(m){this.#e=m},"#showModal","set")},a,{kind:"accessor",name:"#showModal",static:!1,private:!0,access:{has:m=>#t in m,get:m=>m.#t,set:(m,f)=>{m.#t=f}},metadata:g},n,o),ki(this,p={get:ls(function(){return this.#s},"#modalRef","get"),set:ls(function(m){this.#s=m},"#modalRef","set")},u,{kind:"accessor",name:"#modalRef",static:!1,private:!0,access:{has:m=>#r in m,get:m=>m.#r,set:(m,f)=>{m.#r=f}},metadata:g},c,l),ki(null,e={value:s},t,{kind:"class",name:s.name,metadata:g},null,r),h=s=e.value,g&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:g})}static{this.styles=[B,z`
      * {
        box-sizing: border-box;
      }

      dialog {
        padding: 0 0 0 0;
        border: none;
        background: none;

        & section {
          & #controls {
            display: flex;
            justify-content: end;
            margin-bottom: 4px;

            & button {
              padding: 0;
              background: none;
              width: 20px;
              height: 20px;
              pointer: cursor;
              border: none;
              cursor: pointer;
            }
          }
        }
      }
    `]}#e=vr(this,n,!1);get#t(){return d.get.call(this)}set#t(g){return d.set.call(this,g)}#s=(vr(this,o),vr(this,c,null));get#r(){return p.get.call(this)}set#r(g){return p.set.call(this,g)}#i(){this.#r&&(this.#r.open&&this.#r.close(),this.#t=!1)}render(){return this.#t?w`<dialog
      class=${D(this.theme.components.Modal.backdrop)}
      @click=${g=>{let[m]=g.composedPath();m instanceof HTMLDialogElement&&this.#i()}}
      ${pn(g=>{requestAnimationFrame(()=>{!(g&&g instanceof HTMLDialogElement)||g.open||g.showModal()})})}
    >
      <section
        class=${D(this.theme.components.Modal.element)}
        style=${this.theme.additionalStyles?.Modal?W(this.theme.additionalStyles?.Modal):S}
      >
        <div id="controls">
          <button
            @click=${()=>{this.#i()}}
          >
            <span class="g-icon">close</span>
          </button>
        </div>
        <slot></slot>
      </section>
    </dialog>`:w`<section
        @click=${()=>{this.#t=!0}}
      >
        <slot name="entry"></slot>
      </section>`}constructor(){super(...arguments),vr(this,l)}static{vr(s,r)}};return h=s})();var Ti=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},_r=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},Nc=(()=>{let t=[U("a2ui-row")],e,r=[],s,i=F,a,n=[],o=[],d,u=[],c=[];var l=class extends i{static{s=this}static{let p=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[A({reflect:!0,type:String})],d=[A({reflect:!0,type:String})],Ti(this,null,a,{kind:"accessor",name:"alignment",static:!1,private:!1,access:{has:h=>"alignment"in h,get:h=>h.alignment,set:(h,g)=>{h.alignment=g}},metadata:p},n,o),Ti(this,null,d,{kind:"accessor",name:"distribution",static:!1,private:!1,access:{has:h=>"distribution"in h,get:h=>h.distribution,set:(h,g)=>{h.distribution=g}},metadata:p},u,c),Ti(null,e={value:s},t,{kind:"class",name:s.name,metadata:p},null,r),l=s=e.value,p&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:p})}#e=_r(this,n,"stretch");get alignment(){return this.#e}set alignment(p){this.#e=p}#t=(_r(this,o),_r(this,u,"start"));get distribution(){return this.#t}set distribution(p){this.#t=p}static{this.styles=[B,z`
      * {
        box-sizing: border-box;
      }

      :host {
        display: flex;
        flex: var(--weight);
      }

      section {
        display: flex;
        flex-direction: row;
        width: 100%;
        min-height: 100%;
      }

      :host([alignment='start']) section {
        align-items: start;
      }

      :host([alignment='center']) section {
        align-items: center;
      }

      :host([alignment='end']) section {
        align-items: end;
      }

      :host([alignment='stretch']) section {
        align-items: stretch;
      }

      :host([distribution='start']) section {
        justify-content: start;
      }

      :host([distribution='center']) section {
        justify-content: center;
      }

      :host([distribution='end']) section {
        justify-content: end;
      }

      :host([distribution='spaceBetween']) section {
        justify-content: space-between;
      }

      :host([distribution='spaceAround']) section {
        justify-content: space-around;
      }

      :host([distribution='spaceEvenly']) section {
        justify-content: space-evenly;
      }
    `]}render(){return w`<section
      class=${D(this.theme.components.Row)}
      style=${this.theme.additionalStyles?.Row?W(this.theme.additionalStyles?.Row):S}
    >
      <slot></slot>
    </section>`}constructor(){super(...arguments),_r(this,c)}static{_r(s,r)}};return l=s})();var br=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},Ve=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},Mc=(()=>{let t=[U("a2ui-slider")],e,r=[],s,i=F,a,n=[],o=[],d,u=[],c=[],l,p=[],h=[],g,m=[],f=[];var v=class extends i{static{s=this}static{let _=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[A()],d=[A()],l=[A()],g=[A()],br(this,null,a,{kind:"accessor",name:"value",static:!1,private:!1,access:{has:b=>"value"in b,get:b=>b.value,set:(b,k)=>{b.value=k}},metadata:_},n,o),br(this,null,d,{kind:"accessor",name:"minValue",static:!1,private:!1,access:{has:b=>"minValue"in b,get:b=>b.minValue,set:(b,k)=>{b.minValue=k}},metadata:_},u,c),br(this,null,l,{kind:"accessor",name:"maxValue",static:!1,private:!1,access:{has:b=>"maxValue"in b,get:b=>b.maxValue,set:(b,k)=>{b.maxValue=k}},metadata:_},p,h),br(this,null,g,{kind:"accessor",name:"label",static:!1,private:!1,access:{has:b=>"label"in b,get:b=>b.label,set:(b,k)=>{b.label=k}},metadata:_},m,f),br(null,e={value:s},t,{kind:"class",name:s.name,metadata:_},null,r),v=s=e.value,_&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:_})}#e=Ve(this,n,null);get value(){return this.#e}set value(_){this.#e=_}#t=(Ve(this,o),Ve(this,u,0));get minValue(){return this.#t}set minValue(_){this.#t=_}#s=(Ve(this,c),Ve(this,p,0));get maxValue(){return this.#s}set maxValue(_){this.#s=_}#r=(Ve(this,h),Ve(this,m,null));get label(){return this.#r}set label(_){this.#r=_}static{this.styles=[B,z`
      * {
        box-sizing: border-box;
      }

      :host {
        display: block;
        flex: var(--weight);
      }

      input {
        display: block;
        width: 100%;
      }

      .description {
      }
    `]}#i(_){!this.value||!this.processor||"path"in this.value&&this.value.path&&this.processor.setData(this.component,this.value.path,_,this.surfaceId??q.DEFAULT_SURFACE_ID)}#a(_){return w`<section class=${D(this.theme.components.Slider.container)}>
      ${this.label?w`<label class=${D(this.theme.components.Slider.label)} for="data">
            ${xe(this.label,this.component,this.processor,this.surfaceId)}
          </label>`:S}
      <input
        autocomplete="off"
        class=${D(this.theme.components.Slider.element)}
        style=${this.theme.additionalStyles?.Slider?W(this.theme.additionalStyles?.Slider):S}
        @input=${b=>{b.target instanceof HTMLInputElement&&this.#i(b.target.value)}}
        id="data"
        name="data"
        .value=${_}
        type="range"
        min=${this.minValue??"0"}
        max=${this.maxValue??"0"}
      />
      <span class=${D(this.theme.components.Slider.label)}
        >${this.value?un(this.value,this.component,this.processor,this.surfaceId):"0"}</span
      >
    </section>`}render(){if(this.value&&typeof this.value=="object"){if("literalNumber"in this.value&&this.value.literalNumber)return this.#a(this.value.literalNumber);if("literal"in this.value&&this.value.literal!==void 0)return this.#a(this.value.literal);if(this.value&&"path"in this.value&&this.value.path){if(!this.processor||!this.component)return w`(no processor)`;let _=this.processor.getData(this.component,this.value.path,this.surfaceId??q.DEFAULT_SURFACE_ID);return _===null?w`Invalid value`:typeof _!="string"&&typeof _!="number"?w`Invalid value`:this.#a(_)}}return S}constructor(){super(...arguments),Ve(this,f)}static{Ve(s,r)}};return v=s})();var xr=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},Ue=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},Ei=(()=>{let t=[U("a2ui-surface")],e,r=[],s,i=F,a,n=[],o=[],d,u=[],c=[],l,p=[],h=[],g,m=[],f=[];var v=class extends i{static{s=this}static{let _=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[A()],d=[A()],l=[A({attribute:!1})],g=[A()],xr(this,null,a,{kind:"accessor",name:"surfaceId",static:!1,private:!1,access:{has:b=>"surfaceId"in b,get:b=>b.surfaceId,set:(b,k)=>{b.surfaceId=k}},metadata:_},n,o),xr(this,null,d,{kind:"accessor",name:"surface",static:!1,private:!1,access:{has:b=>"surface"in b,get:b=>b.surface,set:(b,k)=>{b.surface=k}},metadata:_},u,c),xr(this,null,l,{kind:"accessor",name:"processor",static:!1,private:!1,access:{has:b=>"processor"in b,get:b=>b.processor,set:(b,k)=>{b.processor=k}},metadata:_},p,h),xr(this,null,g,{kind:"accessor",name:"enableCustomElements",static:!1,private:!1,access:{has:b=>"enableCustomElements"in b,get:b=>b.enableCustomElements,set:(b,k)=>{b.enableCustomElements=k}},metadata:_},m,f),xr(null,e={value:s},t,{kind:"class",name:s.name,metadata:_},null,r),v=s=e.value,_&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:_})}#e=Ue(this,n,null);get surfaceId(){return this.#e}set surfaceId(_){this.#e=_}#t=(Ue(this,o),Ue(this,u,null));get surface(){return this.#t}set surface(_){this.#t=_}#s=(Ue(this,c),Ue(this,p,null));get processor(){return this.#s}set processor(_){this.#s=_}static{this.styles=[z`
      :host {
        display: flex;
        min-height: 0;
        max-height: 100%;
        flex-direction: column;
        gap: 16px;
      }

      #surface-logo {
        display: flex;
        justify-content: center;

        & img {
          width: 50%;
          max-width: 220px;
        }
      }

      a2ui-root {
        flex: 1;
      }
    `]}#r(){return this.surface?.styles.logoUrl?w`<div id="surface-logo">
      <img src=${this.surface.styles.logoUrl} />
    </div>`:S}#i=(Ue(this,h),Ue(this,m,!1));get enableCustomElements(){return this.#i}set enableCustomElements(_){this.#i=_}#a(){let _={};if(this.surface?.styles)for(let[b,k]of Object.entries(this.surface.styles))switch(b){case"primaryColor":{_["--p-100"]="#ffffff",_["--p-99"]=`color-mix(in srgb, ${k} 2%, white 98%)`,_["--p-98"]=`color-mix(in srgb, ${k} 4%, white 96%)`,_["--p-95"]=`color-mix(in srgb, ${k} 10%, white 90%)`,_["--p-90"]=`color-mix(in srgb, ${k} 20%, white 80%)`,_["--p-80"]=`color-mix(in srgb, ${k} 40%, white 60%)`,_["--p-70"]=`color-mix(in srgb, ${k} 60%, white 40%)`,_["--p-60"]=`color-mix(in srgb, ${k} 80%, white 20%)`,_["--p-50"]=k,_["--p-40"]=`color-mix(in srgb, ${k} 80%, black 20%)`,_["--p-35"]=`color-mix(in srgb, ${k} 70%, black 30%)`,_["--p-30"]=`color-mix(in srgb, ${k} 60%, black 40%)`,_["--p-25"]=`color-mix(in srgb, ${k} 50%, black 50%)`,_["--p-20"]=`color-mix(in srgb, ${k} 40%, black 60%)`,_["--p-15"]=`color-mix(in srgb, ${k} 30%, black 70%)`,_["--p-10"]=`color-mix(in srgb, ${k} 20%, black 80%)`,_["--p-5"]=`color-mix(in srgb, ${k} 10%, black 90%)`,_["--0"]="#00000";break}case"font":{_["--font-family"]=k,_["--font-family-flex"]=k;break}}return w`<a2ui-root
      style=${W(_)}
      .surfaceId=${this.surfaceId}
      .processor=${this.processor}
      .childComponents=${this.surface?.componentTree?[this.surface.componentTree]:null}
      .enableCustomElements=${this.enableCustomElements}
    ></a2ui-root>`}render(){return this.surface?w`${[this.#r(),this.#a()]}`:S}constructor(){super(...arguments),Ue(this,f)}static{Ue(s,r)}};return v=s})();var fn=(t,e,r)=>{let s=new Map;for(let i=e;i<=r;i++)s.set(t[i],i);return s},mn=ie(class extends ue{constructor(t){if(super(t),t.type!==Te.CHILD)throw Error("repeat() can only be used in text expressions")}dt(t,e,r){let s;r===void 0?r=e:e!==void 0&&(s=e);let i=[],a=[],n=0;for(let o of t)i[n]=s?s(o,n):n,a[n]=r(o,n),n++;return{values:a,keys:i}}render(t,e,r){return this.dt(t,e,r).values}update(t,[e,r,s]){let i=tn(t),{values:a,keys:n}=this.dt(e,r,s);if(!Array.isArray(i))return this.ut=n,a;let o=this.ut??=[],d=[],u,c,l=0,p=i.length-1,h=0,g=a.length-1;for(;l<=p&&h<=g;)if(i[l]===null)l++;else if(i[p]===null)p--;else if(o[l]===n[h])d[h]=Ke(i[l],a[h]),l++,h++;else if(o[p]===n[g])d[g]=Ke(i[p],a[g]),p--,g--;else if(o[l]===n[g])d[g]=Ke(i[l],a[g]),Lt(t,d[g+1],i[l]),l++,g--;else if(o[p]===n[h])d[h]=Ke(i[p],a[h]),Lt(t,i[l],i[p]),p--,h++;else if(u===void 0&&(u=fn(n,h,g),c=fn(o,l,p)),u.has(o[l]))if(u.has(o[p])){let m=c.get(n[h]),f=m!==void 0?i[m]:null;if(f===null){let v=Lt(t,i[l]);Ke(v,a[h]),d[h]=v}else d[h]=Ke(f,a[h]),Lt(t,i[l],f),i[m]=null;h++}else ts(i[p]),p--;else ts(i[l]),l++;for(;h<=g;){let m=Lt(t,d[g+1]);Ke(m,a[h]),d[h++]=m}for(;l<=p;){let m=i[l++];m!==null&&ts(m)}return this.ut=n,en(t,d),J}});var Ai=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},wr=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},zc=(()=>{let t=[U("a2ui-tabs")],e,r=[],s,i=F,a,n=[],o=[],d,u=[],c=[];var l=class extends i{static{s=this}static{let p=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[A()],d=[A()],Ai(this,null,a,{kind:"accessor",name:"titles",static:!1,private:!1,access:{has:h=>"titles"in h,get:h=>h.titles,set:(h,g)=>{h.titles=g}},metadata:p},n,o),Ai(this,null,d,{kind:"accessor",name:"selected",static:!1,private:!1,access:{has:h=>"selected"in h,get:h=>h.selected,set:(h,g)=>{h.selected=g}},metadata:p},u,c),Ai(null,e={value:s},t,{kind:"class",name:s.name,metadata:p},null,r),l=s=e.value,p&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:p})}#e=wr(this,n,null);get titles(){return this.#e}set titles(p){this.#e=p}#t=(wr(this,o),wr(this,u,0));get selected(){return this.#t}set selected(p){this.#t=p}static{this.styles=[B,z`
      :host {
        display: block;
        flex: var(--weight);
      }
    `]}willUpdate(p){if(super.willUpdate(p),p.has("selected")){for(let g of this.children)g.removeAttribute("slot");let h=this.children[this.selected];if(!h)return;h.slot="current"}}#s(){return this.titles?w`<div id="buttons" class=${D(this.theme.components.Tabs.element)}>
      ${mn(this.titles,(p,h)=>{let g="";if("literalString"in p&&p.literalString)g=p.literalString;else if("literal"in p&&p.literal!==void 0)g=p.literal;else if(p&&"path"in p&&p.path){if(!this.processor||!this.component)return w`(no model)`;let f=this.processor.getData(this.component,p.path,this.surfaceId??q.DEFAULT_SURFACE_ID);if(typeof f!="string")return w`(invalid)`;g=f}let m;return this.selected===h?m=ke.merge(this.theme.components.Tabs.controls.all,this.theme.components.Tabs.controls.selected):m={...this.theme.components.Tabs.controls.all},w`<button
          ?disabled=${this.selected===h}
          class=${D(m)}
          @click=${()=>{this.selected=h}}
        >
          ${g}
        </button>`})}
    </div>`:S}#r(){return w`<slot name="current"></slot>`}render(){return w`<section
      class=${D(this.theme.components.Tabs.container)}
      style=${this.theme.additionalStyles?.Tabs?W(this.theme.additionalStyles?.Tabs):S}
    >
      ${[this.#s(),this.#r()]}
    </section>`}constructor(){super(...arguments),wr(this,c)}static{wr(s,r)}};return l=s})();var $r=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},Le=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},Ii=(()=>{let t=[U("a2ui-textfield")],e,r=[],s,i=F,a,n=[],o=[],d,u=[],c=[],l,p=[],h=[],g,m=[],f=[];var v=class extends i{static{s=this}static{let _=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[A()],d=[A()],l=[A()],g=[A()],$r(this,null,a,{kind:"accessor",name:"text",static:!1,private:!1,access:{has:b=>"text"in b,get:b=>b.text,set:(b,k)=>{b.text=k}},metadata:_},n,o),$r(this,null,d,{kind:"accessor",name:"label",static:!1,private:!1,access:{has:b=>"label"in b,get:b=>b.label,set:(b,k)=>{b.label=k}},metadata:_},u,c),$r(this,null,l,{kind:"accessor",name:"textFieldType",static:!1,private:!1,access:{has:b=>"textFieldType"in b,get:b=>b.textFieldType,set:(b,k)=>{b.textFieldType=k}},metadata:_},p,h),$r(this,null,g,{kind:"accessor",name:"validationRegexp",static:!1,private:!1,access:{has:b=>"validationRegexp"in b,get:b=>b.validationRegexp,set:(b,k)=>{b.validationRegexp=k}},metadata:_},m,f),$r(null,e={value:s},t,{kind:"class",name:s.name,metadata:_},null,r),v=s=e.value,_&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:_})}#e=Le(this,n,null);get text(){return this.#e}set text(_){this.#e=_}#t=(Le(this,o),Le(this,u,null));get label(){return this.#t}set label(_){this.#t=_}#s=(Le(this,c),Le(this,p,null));get textFieldType(){return this.#s}set textFieldType(_){this.#s=_}#r=(Le(this,h),Le(this,m,null));get validationRegexp(){return this.#r}set validationRegexp(_){this.#r=_}static{this.styles=[B,z`
      * {
        box-sizing: border-box;
      }

      :host {
        display: flex;
        flex: var(--weight);
      }

      input {
        display: block;
        width: 100%;
      }

      input:invalid {
        border-color: var(--color-error);
        color: var(--color-error);
        outline-color: var(--color-error);
      }

      input:invalid:focus {
        border-color: var(--color-error);
        outline-color: var(--color-error);
      }

      label {
        display: block;
        margin-bottom: 4px;
      }
    `]}#i(_){!this.text||!this.processor||"path"in this.text&&this.text.path&&this.processor.setData(this.component,this.text.path,_,this.surfaceId??q.DEFAULT_SURFACE_ID)}#a(_,b){return w` <section class=${D(this.theme.components.TextField.container)}>
      ${b&&b!==""?w`<label class=${D(this.theme.components.TextField.label)} for="data"
            >${b}</label
          >`:S}
      <input
        autocomplete="off"
        class=${D(this.theme.components.TextField.element)}
        style=${this.theme.additionalStyles?.TextField?W(this.theme.additionalStyles?.TextField):S}
        @input=${k=>{k.target instanceof HTMLInputElement&&(this.dispatchEvent(new Er.A2UIValidationEvent({componentId:this.id,value:k.target.value,valid:k.target.checkValidity()})),this.#i(k.target.value))}}
        name="data"
        id="data"
        .value=${_}
        .placeholder=${"Please enter a value"}
        pattern=${this.validationRegexp&&Zs(this.validationRegexp)?this.validationRegexp:S}
        type=${this.textFieldType==="number"?"number":"text"}
      />
    </section>`}render(){let _=xe(this.label,this.component,this.processor,this.surfaceId),b=xe(this.text,this.component,this.processor,this.surfaceId);return this.#a(b,_)}constructor(){super(...arguments),Le(this,f)}static{Le(s,r)}};return v=s})();var Sr=class extends ue{constructor(e){if(super(e),this.it=S,e.type!==Te.CHILD)throw Error(this.constructor.directiveName+"() can only be used in child bindings")}render(e){if(e===S||e==null)return this._t=void 0,this.it=e;if(e===J)return e;if(typeof e!="string")throw Error(this.constructor.directiveName+"() called with a non-string value");if(e===this.it)return this._t;this.it=e;let r=[e];return r.raw=r,this._t={_$litType$:this.constructor.resultType,strings:r,values:[]}}};Sr.directiveName="unsafeHTML",Sr.resultType=1;var Ri=ie(Sr);var cs=class{constructor(e){this.G=e}disconnect(){this.G=void 0}reconnect(e){this.G=e}deref(){return this.G}},us=class{constructor(){this.Y=void 0,this.Z=void 0}get(){return this.Y}pause(){this.Y??=new Promise(e=>this.Z=e)}resume(){this.Z?.(),this.Y=this.Z=void 0}};var gn=t=>!Ja(t)&&typeof t.then=="function",yn=1073741823,Oi=class extends Ye{constructor(){super(...arguments),this._$Cwt=yn,this._$Cbt=[],this._$CK=new cs(this),this._$CX=new us}render(...e){return e.find(r=>!gn(r))??J}update(e,r){let s=this._$Cbt,i=s.length;this._$Cbt=r;let a=this._$CK,n=this._$CX;this.isConnected||this.disconnected();for(let o=0;o<r.length&&!(o>this._$Cwt);o++){let d=r[o];if(!gn(d))return this._$Cwt=o,d;o<i&&d===s[o]||(this._$Cwt=yn,i=0,Promise.resolve(d).then(async u=>{for(;n.get();)await n.get();let c=a.deref();if(c!==void 0){let l=c._$Cbt.indexOf(d);l>-1&&l<c._$Cwt&&(c._$Cwt=l,c.setValue(u))}}))}return J}disconnected(){this._$CK.disconnect(),this._$CX.pause()}reconnected(){this._$CK.reconnect(this),this._$CX.resume()}},ji=ie(Oi);var Pi=class t extends ue{#e=null;#t=null;update(e,[r,s,i]){let a=JSON.stringify(i?.tagClassMap);return this.#e===r&&a===this.#t?J:(this.#e=r,this.#t=a,this.render(r,s,i))}static{this.defaultMarkdownWarningLogged=!1}render(e,r,s){if(r){let a=r(e,s).then(n=>Ri(n));return ji(a,w`<span class="no-markdown-renderer">${e}</span>`)}let i=(async()=>{try{let{renderMarkdown:a}=await import("@a2ui/markdown-it"),n=await a(e,s);return Ri(n)}catch{return t.defaultMarkdownWarningLogged||(console.warn("[MarkdownDirective] Failed to load optional `@a2ui/markdown-it` renderer. Using fallback regex."),t.defaultMarkdownWarningLogged=!0),w`<span class="no-markdown-renderer">${e}</span>`}})();return ji(i,w`<span class="no-markdown-renderer">${e}</span>`)}},Di=ie(Pi);var Cr={};Ht(Cr,{markdown:()=>Ni,theme:()=>on,themeContext:()=>yi});var Ni=Symbol("A2UIMarkdown");var ds=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},St=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},Mi=(()=>{let t=[U("a2ui-text")],e,r=[],s,i=F,a,n=[],o=[],d,u=[],c=[],l,p=[],h=[];var g=class extends i{static{s=this}static{let m=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[A()],d=[A({reflect:!0,attribute:"usage-hint"})],l=[hr({context:Ni})],ds(this,null,a,{kind:"accessor",name:"text",static:!1,private:!1,access:{has:f=>"text"in f,get:f=>f.text,set:(f,v)=>{f.text=v}},metadata:m},n,o),ds(this,null,d,{kind:"accessor",name:"usageHint",static:!1,private:!1,access:{has:f=>"usageHint"in f,get:f=>f.usageHint,set:(f,v)=>{f.usageHint=v}},metadata:m},u,c),ds(this,null,l,{kind:"accessor",name:"markdownRenderer",static:!1,private:!1,access:{has:f=>"markdownRenderer"in f,get:f=>f.markdownRenderer,set:(f,v)=>{f.markdownRenderer=v}},metadata:m},p,h),ds(null,e={value:s},t,{kind:"class",name:s.name,metadata:m},null,r),g=s=e.value,m&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:m})}#e=St(this,n,null);get text(){return this.#e}set text(m){this.#e=m}#t=(St(this,o),St(this,u,null));get usageHint(){return this.#t}set usageHint(m){this.#t=m}#s=(St(this,c),St(this,p,void 0));get markdownRenderer(){return this.#s}set markdownRenderer(m){this.#s=m}static{this.styles=[B,z`
      :host {
        display: block;
        flex: var(--weight);
      }

      h1,
      h2,
      h3,
      h4,
      h5 {
        line-height: inherit;
        font: inherit;
      }
    `]}#r(){let m=null;if(this.text&&typeof this.text=="object"){if("literalString"in this.text&&this.text.literalString)m=this.text.literalString;else if("literal"in this.text&&this.text.literal!==void 0)m=this.text.literal;else if(this.text&&"path"in this.text&&this.text.path){if(!this.processor||!this.component)return w`(no model)`;let v=this.processor.getData(this.component,this.text.path,this.surfaceId??q.DEFAULT_SURFACE_ID);v!=null&&(m=v.toString())}}if(m==null)return w`(empty)`;let f=m;switch(this.usageHint){case"h1":f=`# ${f}`;break;case"h2":f=`## ${f}`;break;case"h3":f=`### ${f}`;break;case"h4":f=`#### ${f}`;break;case"h5":f=`##### ${f}`;break;case"caption":f=`*${f}*`;break;default:break}return w`${Di(f,this.markdownRenderer,{tagClassMap:ke.appendToAll(this.theme.markdown,["ol","ul","li"],{})})}`}#i(m){return typeof m!="object"||Array.isArray(m)||!m?!1:["h1","h2","h3","h4","h5","h6","caption","body"].every(v=>v in m)}#a(){let m={},f=this.theme.additionalStyles?.Text;if(!f)return m;if(this.#i(f)){let v=this.usageHint??"body";m=f[v]}else m=f;return m}render(){let m=ke.merge(this.theme.components.Text.all,this.usageHint?this.theme.components.Text[this.usageHint]:{});return w`<section
      class=${D(m)}
      style=${this.theme.additionalStyles?.Text?W(this.#a()):S}
    >
      ${this.#r()}
    </section>`}constructor(){super(...arguments),St(this,h)}static{St(s,r)}};return g=s})();var vn=function(t,e,r,s,i,a){function n(v){if(v!==void 0&&typeof v!="function")throw new TypeError("Function expected");return v}for(var o=s.kind,d=o==="getter"?"get":o==="setter"?"set":"value",u=!e&&t?s.static?t:t.prototype:null,c=e||(u?Object.getOwnPropertyDescriptor(u,s.name):{}),l,p=!1,h=r.length-1;h>=0;h--){var g={};for(var m in s)g[m]=m==="access"?{}:s[m];for(var m in s.access)g.access[m]=s.access[m];g.addInitializer=function(v){if(p)throw new TypeError("Cannot add initializers after decoration has completed");a.push(n(v||null))};var f=(0,r[h])(o==="accessor"?{get:c.get,set:c.set}:c[d],g);if(o==="accessor"){if(f===void 0)continue;if(f===null||typeof f!="object")throw new TypeError("Object expected");(l=n(f.get))&&(c.get=l),(l=n(f.set))&&(c.set=l),(l=n(f.init))&&i.unshift(l)}else(l=n(f))&&(o==="field"?i.unshift(l):c[d]=l)}u&&Object.defineProperty(u,s.name,c),p=!0},zi=function(t,e,r){for(var s=arguments.length>2,i=0;i<e.length;i++)r=s?e[i].call(t,r):e[i].call(t);return s?r:void 0},Vc=(()=>{let t=[U("a2ui-video")],e,r=[],s,i=F,a,n=[],o=[];var d=class extends i{static{s=this}static{let u=typeof Symbol=="function"&&Symbol.metadata?Object.create(i[Symbol.metadata]??null):void 0;a=[A()],vn(this,null,a,{kind:"accessor",name:"url",static:!1,private:!1,access:{has:c=>"url"in c,get:c=>c.url,set:(c,l)=>{c.url=l}},metadata:u},n,o),vn(null,e={value:s},t,{kind:"class",name:s.name,metadata:u},null,r),d=s=e.value,u&&Object.defineProperty(s,Symbol.metadata,{enumerable:!0,configurable:!0,writable:!0,value:u})}#e=zi(this,n,null);get url(){return this.#e}set url(u){this.#e=u}static{this.styles=[B,z`
      * {
        box-sizing: border-box;
      }

      :host {
        display: block;
        flex: var(--weight);
        min-height: 0;
        overflow: auto;
      }

      video {
        display: block;
        width: 100%;
      }
    `]}#t(){if(!this.url)return S;let u=c=>{let l=wt(c);return l?w`<video controls src=${l} />`:w`Invalid video URL`};if(this.url&&typeof this.url=="object"){if("literalString"in this.url)return u(this.url.literalString);if("literal"in this.url)return u(this.url.literal);if(this.url&&"path"in this.url&&this.url.path){if(!this.processor||!this.component)return w`(no processor)`;let c=this.processor.getData(this.component,this.url.path,this.surfaceId??q.DEFAULT_SURFACE_ID);return u(c)}}return w`(empty)`}render(){return w`<section
      class=${D(this.theme.components.Video)}
      style=${this.theme.additionalStyles?.Video?W(this.theme.additionalStyles?.Video):S}
    >
      ${this.#t()}
    </section>`}constructor(){super(...arguments),zi(this,o)}static{zi(s,r)}};return d=s})();Ei.prototype.render=function(){return w`<a2ui-root .surfaceId=${this.surfaceId} .processor=${this.processor} .childComponents=${this.surface?.componentTree?[this.surface.componentTree]:null} .enableCustomElements=${!1}></a2ui-root>`};Mi.prototype.render=function(){let t=this.text?.path?this.processor?.getData(this.component,this.text.path,this.surfaceId)||"":this.text?.literalString||"";return this.usageHint==="h3"?w`<h3>${t}</h3>`:w`<span>${t}</span>`};function _n(t,e,r,s){let i=e?.path?t.processor?.getData(t.component,e.path,t.surfaceId)||"":e?.literalString||"";return w`<section><label for="data">${r}</label><input id="data" name=${t.id}
    type=${s} required maxlength="1000" autocomplete=${t.id==="email"?"email":"off"}
    .value=${i} @input=${a=>t.processor.setData(t.component,e.path,a.target.value,t.surfaceId)}></section>`}Ii.prototype.render=function(){return _n(this,this.text,this.label?.literalString||"",this.id==="email"?"email":"text")};wi.prototype.render=function(){return _n(this,this.value,"Preferred date and time (required)","datetime-local")};var Vi=new CSSStyleSheet;Vi.replaceSync(":host{font:16px/1.5 system-ui;min-width:0;color:inherit}:host(a2ui-surface){color:#241238}*{box-sizing:border-box}section{width:100%}input,button{font:inherit;min-height:48px;border-radius:8px;padding:10px;width:100%}input{border:1px solid #767676;background:white;color:#241238}button{background:#6d28d9;color:white;border:0;cursor:pointer}button:disabled{opacity:.6}label{display:block;margin-bottom:4px}input:focus-visible,button:focus-visible{outline:3px solid #5b21b6;outline-offset:2px}input:user-invalid{border:2px solid #b91c1c}slot{white-space:normal}a2ui-column{gap:12px}section{gap:12px}h3{font-size:1.1rem;margin:0}p{margin:0 0 8px}:host(a2ui-card){background:#fff;border:1px solid #c4b5fd;border-radius:12px;padding:16px}");function hs(t){let e=[];for(let r of t.querySelectorAll("*"))e.push(r),r.shadowRoot&&e.push(...hs(r.shadowRoot));return e}window.ConciergeA2UI={create(t,e){let r={components:{Card:{},Column:{},Button:{},Text:{all:{},h3:{}},TextField:{container:{},label:{},element:{}},DateTimeInput:{container:{},label:{},element:{}}}};t.addEventListener("context-request",l=>{l.context===Cr.theme&&(l.stopPropagation(),l.callback(r))});let s=Ea.createSignalA2uiMessageProcessor(),i=new Map,a=new Set,n=new Set;function o(){for(let l of hs(t)){if(l.shadowRoot&&!l.shadowRoot.adoptedStyleSheets.includes(Vi)&&(l.shadowRoot.adoptedStyleSheets=[...l.shadowRoot.adoptedStyleSheets,Vi]),l.matches("input")){let p=l.getRootNode().host,h=p?.id;if(l.required=!0,l.maxLength=1e3,l.name=h||"value",h==="email"&&(l.type="email",l.autocomplete="email"),h==="timezone"&&(l.autocomplete="off"),h==="when"){let m=l.getRootNode().querySelector("label");m&&m.textContent!=="Preferred date and time (required)"&&(m.textContent="Preferred date and time (required)")}let g=p?.surfaceId;l.disabled=a.has(g)||n.has(g)}if(l.matches("button")){let p=l.getRootNode().host?.surfaceId;l.type="button",l.disabled=a.has(p)||n.has(p)}}}let d=new MutationObserver(o);d.observe(t,{childList:!0,subtree:!0});async function u(){for(let l=0;l<12;l++){let p=hs(t);await Promise.all(p.filter(h=>h.updateComplete).map(h=>h.updateComplete));for(let h of p)h.shadowRoot&&d.observe(h.shadowRoot,{childList:!0,subtree:!0});o()}}async function c(l){s.processMessages([l]);for(let[p,h]of s.getSurfaces()){let g=i.get(p);g||(g=document.createElement("a2ui-surface"),g.dataset.surfaceId=p,g.surfaceId=p,g.processor=s,g.enableCustomElements=!1,i.set(p,g),t.append(g)),g.surface=h,g.requestUpdate()}for(let[p,h]of i)s.getSurfaces().has(p)||(h.remove(),i.delete(p));await u()}return t.addEventListener("a2uiaction",async l=>{let p=l.detail;if(p.eventType!=="a2ui.action")return;let h=l.composedPath().find(f=>f.localName==="a2ui-surface");if(!h||a.has(h.surfaceId)||n.has(h.surfaceId))return;let g=hs(h.shadowRoot).filter(f=>f.matches("input"));for(let f of g)if(!f.reportValidity()){f.focus();return}let m={};for(let f of p.action.context||[])m[f.key]=f.value.path?s.getData(p.sourceComponent,f.value.path,h.surfaceId):f.value.literalString;n.add(h.surfaceId),o();try{await e({userAction:{name:p.action.name,surfaceId:h.surfaceId,sourceComponentId:p.sourceComponentId,timestamp:new Date().toISOString(),context:m}}),a.add(h.surfaceId)}catch{}finally{n.delete(h.surfaceId),o()}}),{receive:c}}};})();
/*! Bundled license information:

signal-polyfill/dist/index.js:
  (**
   * @license
   * Copyright Google LLC All Rights Reserved.
   *
   * Use of this source code is governed by an MIT-style license that can be
   * found in the LICENSE file at https://angular.io/license
   *)
  (**
   * @license
   * Copyright 2024 Bloomberg Finance L.P.
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *     http://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)

@lit/reactive-element/css-tag.js:
  (**
   * @license
   * Copyright 2019 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

@lit/reactive-element/reactive-element.js:
lit-html/lit-html.js:
lit-element/lit-element.js:
@lit/reactive-element/decorators/custom-element.js:
@lit/reactive-element/decorators/property.js:
@lit/reactive-element/decorators/state.js:
@lit/reactive-element/decorators/event-options.js:
@lit/reactive-element/decorators/base.js:
@lit/reactive-element/decorators/query.js:
@lit/reactive-element/decorators/query-all.js:
@lit/reactive-element/decorators/query-async.js:
@lit/reactive-element/decorators/query-assigned-nodes.js:
lit-html/directive.js:
lit-html/async-directive.js:
@lit/context/lib/decorators/provide.js:
lit-html/directives/repeat.js:
lit-html/directives/unsafe-html.js:
lit-html/directives/until.js:
  (**
   * @license
   * Copyright 2017 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

lit-html/is-server.js:
@lit/context/lib/decorators/consume.js:
  (**
   * @license
   * Copyright 2022 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

@lit/reactive-element/decorators/query-assigned-elements.js:
@lit/context/lib/context-request-event.js:
@lit/context/lib/create-context.js:
@lit/context/lib/controllers/context-consumer.js:
@lit/context/lib/value-notifier.js:
@lit/context/lib/controllers/context-provider.js:
@lit/context/lib/context-root.js:
lit-html/directives/map.js:
lit-html/directives/private-async-helpers.js:
  (**
   * @license
   * Copyright 2021 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

@lit-labs/signals/lib/signal-watcher.js:
@lit-labs/signals/lib/watch.js:
@lit-labs/signals/lib/html-tag.js:
@lit-labs/signals/index.js:
  (**
   * @license
   * Copyright 2023 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

lit-html/directive-helpers.js:
lit-html/directives/ref.js:
  (**
   * @license
   * Copyright 2020 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

lit-html/directives/class-map.js:
lit-html/directives/style-map.js:
  (**
   * @license
   * Copyright 2018 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)
*/
