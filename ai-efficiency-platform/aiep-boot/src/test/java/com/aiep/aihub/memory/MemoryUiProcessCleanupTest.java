package com.aiep.aihub.memory;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

/** 无数据库、浏览器或业务服务的本任务多层进程超时兜底验证。 */
class MemoryUiProcessCleanupTest {
    @Test void timeoutCleanupStopsOnlyCapturedRootAndItsRealDescendants()throws Exception{
        Path root=Path.of(System.getProperty("user.dir")).toAbsolutePath();
        while(root!=null&&!Files.isDirectory(root.resolve("efficiency-platform-agent")))root=root.getParent();
        assertNotNull(root);
        String child="import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); time.sleep(120)";
        String parent="import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',"+new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(child)+"]); time.sleep(120)";
        Path script=Files.createTempFile("aiep-memory-process-",".py");
        Files.writeString(script,parent,java.nio.charset.StandardCharsets.UTF_8);
        var process=new ProcessBuilder(root.resolve("efficiency-platform-agent/.venv/Scripts/python.exe").toString(),script.toString()).start();
        var descendants=new ArrayList<ProcessHandle>();
        try{
            long ready=System.nanoTime()+TimeUnit.SECONDS.toNanos(8);
            while(System.nanoTime()<ready){descendants.clear();process.descendants().forEach(descendants::add);if(descendants.size()>=2)break;Thread.sleep(10);}
            if(!process.isAlive())throw new AssertionError("无害进程探针启动失败："+new String(process.getErrorStream().readAllBytes(),java.nio.charset.StandardCharsets.UTF_8));
            assertTrue(descendants.size()>=2,"必须实际启动独立子进程和孙进程；actual="+descendants.size());
            MemoryUiIntegrationTest.stopOwnedBrowser(process);
            long stopped=System.nanoTime()+TimeUnit.SECONDS.toNanos(2);
            while(System.nanoTime()<stopped&&descendants.stream().anyMatch(ProcessHandle::isAlive))Thread.sleep(10);
            assertFalse(process.isAlive());
            assertTrue(descendants.stream().noneMatch(ProcessHandle::isAlive),"超时兜底不得只停止根包装器而遗留本任务子孙进程");
        }finally{
            descendants.forEach(handle->{if(handle.isAlive())handle.destroyForcibly();});
            if(process.isAlive())process.destroyForcibly();process.waitFor(5,TimeUnit.SECONDS);
            Files.deleteIfExists(script);
        }
    }
}
