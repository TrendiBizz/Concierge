/* Fixed-purpose local launcher: the approved script hash is baked into the
 * executable receiving macOS Full Disk Access. No arbitrary command/argv. */
#include <CommonCrypto/CommonDigest.h>
#include <mach-o/dyld.h>
#include <sys/stat.h>
#include <unistd.h>
#include <pwd.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef APPROVED_SCRIPT_SHA256
#error Approved script hash required
#endif

int main(int argc,char **argv) {
    char binary[PATH_MAX],resolved[PATH_MAX],script[PATH_MAX],config[PATH_MAX];
    uint32_t size=sizeof(binary);
    if(_NSGetExecutablePath(binary,&size)||!realpath(binary,resolved))return 1;
    char *slash=strrchr(resolved,'/');if(!slash)return 1;*slash=0;
    if(snprintf(script,sizeof(script),"%s/../Resources/mac_sms_agent.py",resolved)>=sizeof(script))return 1;
    struct stat st;
    if(lstat(script,&st)||!S_ISREG(st.st_mode)||(st.st_mode&022)||(st.st_uid!=getuid()&&st.st_uid!=0))return 2;
    FILE *file=fopen(script,"rb");if(!file)return 2;
    CC_SHA256_CTX ctx;CC_SHA256_Init(&ctx);
    unsigned char buffer[8192],digest[CC_SHA256_DIGEST_LENGTH];size_t length;
    while((length=fread(buffer,1,sizeof(buffer),file)))CC_SHA256_Update(&ctx,buffer,(CC_LONG)length);
    if(ferror(file)){fclose(file);return 2;}fclose(file);CC_SHA256_Final(digest,&ctx);
    char hash[65];for(int i=0;i<32;i++)snprintf(hash+2*i,3,"%02x",digest[i]);
    if(strcmp(hash,APPROVED_SCRIPT_SHA256)){fprintf(stderr,"Phone connector code changed; rebuild the approved app.\n");return 3;}
    if(argc==2&&!strcmp(argv[1],"--probe")) {
        execl("/usr/bin/python3","python3","-I","-B",script,"--probe",(char*)NULL);
        return 4;
    }
    if(argc!=1)return 4;
    struct passwd *owner=getpwuid(getuid());if(!owner)return 4;
    if(snprintf(config,sizeof(config),"%s/.config/trendi-phone/config.json",owner->pw_dir)>=sizeof(config))return 4;
    if(lstat(config,&st)||!S_ISREG(st.st_mode)||(st.st_mode&077)||st.st_uid!=getuid())return 4;
    execl("/usr/bin/python3","python3","-I","-B",script,"--config",config,(char*)NULL);
    return 4;
}
